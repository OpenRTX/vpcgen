#!/usr/bin/env python3

import csv
import getopt
import json
import ntpath
import os
import re
import shutil
import subprocess
import sys
import urllib.request

MAX_TRANSFER_SIZE = 32
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
overwrite=False
gain='0'
atempo='1.25'
removeSilenceAtStart = False
# PollyPro is not working
forceTTSMP3Usage = True



def convertToRaw(inFile,outFile):
    print("ConvertToRaw "+ inFile + " -> " + outFile + " gain="+gain + " tempo="+atempo)
    callArgs = ['ffmpeg','-y','-i', inFile,'-filter:a','atempo=+'+atempo+',volume='+gain+'dB','-ar','8000','-f','s16le',outFile]
    if os.name == 'nt':
        subprocess.call(callArgs, creationflags=CREATE_NO_WINDOW)#'-af','silenceremove=1:0:-50dB'
    elif os.name == 'posix':
        subprocess.call(callArgs)#'-af','silenceremove=1:0:-50dB'


def convertToCodec2(inFile,outFile):
    print("ConvertToCodec2 "+ inFile + " -> " + outFile)
    callArgs = ['c2enc','3200',inFile,outFile]
    if os.name == 'nt':
        subprocess.call(callArgs, creationflags=CREATE_NO_WINDOW, shell=True)
    elif os.name == 'posix':
        subprocess.call(callArgs)


def downloadPollyPro(voiceName,fileStub,promptText,speechSpeed):
    retval=True
    hasDownloaded = False
    myobj = {'text-input': promptText,
             'voice':voiceName,
             'format':'mp3',# mp3 or ogg_vorbis or json
             'frequency':'22050',
             'effect':speechSpeed}

    data = urllib.parse.urlencode(myobj)
    data = data.encode('ascii')

    mp3FileName = voiceName + "/" +fileStub+".mp3"
    rawFileName = voiceName + "/" +fileStub+".raw"
    Codec2Filename = voiceName + "/" +fileStub+".c2"
    if (not os.path.exists(mp3FileName) or overwrite):
        with urllib.request.urlopen("https://voicepolly.pro/speech-converter.php", data) as f:
            resp = f.read().decode('utf-8')
            print("PollyPro: Downloading synthesised speech for text: \"" + promptText + "\" -> " + mp3FileName)
            if resp.endswith('.mp3'):
                with urllib.request.urlopen(resp) as response, open(mp3FileName, 'wb') as out_file:
                    audioData = response.read() # a `bytes` object
                    out_file.write(audioData)
                    hasDownloaded = True
                    retval = True
            else:
                print("Error requesting sound " + resp)
                retval=False
#    else:
#        print("Download skipping " + file_name)

    if (hasDownloaded or not os.path.exists(rawFileName) or overwrite):
        convertToRaw(mp3FileName,rawFileName)
        if (os.path.exists(Codec2Filename)):
            os.remove(Codec2Filename)# Codec2 file is now out of date, so delete it
    if (not os.path.exists(Codec2Filename)):
        convertToCodec2(rawFileName, Codec2Filename)
    return retval


def downloadTTSMP3(voiceName,fileStub,promptText):
    myobj = {'msg': promptText,
             'lang':voiceName,
             'source':'ttsmp3.com'}

    data = urllib.parse.urlencode(myobj)
    myStr = str.replace(data,"+","%20") #hacky fix because urlencode is not encoding spaces to %20
    data = myStr.encode('ascii')


    mp3FileName = voiceName + "/" + fileStub + ".mp3"
    rawFileName = voiceName + "/" + fileStub + "_" + atempo + ".raw"
    Codec2Filename = voiceName + "/" + fileStub + "_" + atempo + ".c2"
    hasDownloaded = False

    if (not os.path.exists(mp3FileName) or overwrite):
        print("Download TTSMP3 " +  promptText)
        with urllib.request.urlopen("https://ttsmp3.com/makemp3_new.php", data) as f:
            resp = f.read().decode('utf-8')
            print("TTSMP3: Downloading synthesised speech for text: \"" + promptText + "\" -> " + mp3FileName)
            print(resp)
            data = json.loads(resp)
            if (data['Error'] == 0):
                print(data['URL'])
                # Download the file from `url` and save it locally under `file_name`:
                with urllib.request.urlopen(data['URL']) as response, open(mp3FileName, 'wb') as out_file:
                    mp3data = response.read() # a `bytes` object
                    out_file.write(mp3data)
                    ## need to resample to 8kHz sample rate because ttsmp3 files are 22.05kHz
                    out_file.close()
                    hasDownloaded = True

            else:
                print("Error requesting sound")
                return False

    if (hasDownloaded or not os.path.exists(rawFileName) or overwrite):
        convertToRaw(mp3FileName,rawFileName)
        if (os.path.exists(Codec2Filename)):
            os.remove(Codec2Filename)# codec2 file is now out of date, so delete it
    if (not os.path.exists(Codec2Filename)):
        convertToCodec2(rawFileName,Codec2Filename)
    return True


def downloadSpeechForWordList(filename,voiceName):
    retval = True
    speechSpeed="normal"

    opener = urllib.request.build_opener()
    opener.addheaders = [('User-Agent', 'VoicePromptsBuilder for OpenRTX')]
    urllib.request.install_opener(opener)

    with open(filename,"r",encoding='utf-8') as csvfile:
        reader = csv.DictReader(filter(lambda row: row[0]!='#', csvfile))
        for row in reader:
            promptName = row['PromptName'].strip()

            speechPrefix = row['PromptSpeechPrefix'].strip()

            ## PollyPro is not working.
            if (not forceTTSMP3Usage) and (speechPrefix != "") and False:
                #Use VoicePolly as its not a special SSML that it doesnt handle
                if (speechPrefix.find("<prosody rate=")!=-1):
                    matchObj = re.search(r'\".*\"',speechPrefix)
                    if (matchObj):
                        speechSpeed = matchObj.group(0)[1:-1]

                downloadPollyPro(voiceName, promptName, row['PromptText'], speechSpeed)
            else:
                promptTTSText = row['PromptSpeechPrefix'].strip() +  row['PromptText'] + row['PromptSpeechPostfix'].strip()

                if not downloadTTSMP3(voiceName, promptName, promptTTSText):
                    retval=False
                    break
        # Add voice name as last prompt
        if not downloadTTSMP3(voiceName, "PROMPT_VOICE_NAME", voiceName):
            retval=False
        return retval


def buildDataPack(filename,voiceName,outputFileName):
    print("Building...")
    promptsDict={}#create an empty dictionary
    with open(filename,"r",encoding='utf-8') as csvfile:
        reader = csv.DictReader(filter(lambda row: row[0]!='#', csvfile))
        for row in reader:
            promptName = row['PromptName'].strip()
            infile = voiceName + "/" + promptName + "_" + atempo + ".c2"
            with open(infile,'rb') as f:
                promptsDict[promptName] = bytearray(f.read())
                f.close()
        promptName = "PROMPT_VOICE_NAME"
        infile = voiceName + "/" + promptName + "_" + atempo + ".c2"
        with open(infile,'rb') as f:
            promptsDict[promptName] = bytearray(f.read())
            f.close()
                
    MAX_PROMPTS = 350
    headerTOCSize = (MAX_PROMPTS * 4) + 4 + 4
    outBuf = bytearray(headerTOCSize)
    outBuf[0:3]  = bytes([0x56, 0x50, 0x00, 0x00])#Magic number
    outBuf[4:7]  = bytes([0x00, 0x10, 0x00, 0x00])#Version number
    outBuf[8:11] = bytes([0x00, 0x00, 0x00, 0x00])#First prompt audio is at offset zero
    bufPos=12
    cumulativelength=0
    for prompt in promptsDict:
        cumulativelength = cumulativelength + len(promptsDict[prompt])
        outBuf[bufPos+3] = (cumulativelength >> 24) & 0xFF
        outBuf[bufPos+2] = (cumulativelength >> 16) & 0xFF
        outBuf[bufPos+1] = (cumulativelength >>  8) & 0xFF
        outBuf[bufPos+0] = (cumulativelength >>  0) & 0xFF
        bufPos = bufPos + 4
    #outputFileName = voiceName+'/voice_prompts_'+voiceName+'.bin'
    with open(outputFileName,'wb') as f:
        f.write(outBuf[0:headerTOCSize])#Should be headerTOCSize
        for prompt in promptsDict:
            f.write(promptsDict[prompt])
    f.close()
    print("Built voice pack "+outputFileName)


PROGRAM_VERSION = "0.0.3"

def usage(message=""):
    print("OpenRTX voice prompts creator. v" + PROGRAM_VERSION)
    if (message != ""):
        print()
        print(message)
        print()

    print("Usage:  " + ntpath.basename(sys.argv[0]) + " [OPTION]")
    print("")
    print("    -h Display this help text,")
    print("    -c Configuration file (csv) - using this overrides all other options")
    print("    -f=<wordlist_csv_file> : Wordlist file. Required for most functions")
    ##print("    -n=<Voice_name>       : Voice name for synthesised speech from Voicepolly.pro and temporary folder name")
    ##print("    -s                    : Download synthesised speech from Voicepolly.pro")
    print("    -T                    : Download synthesised speech from ttsmp3.com")
    print("    -b                    : Build voice prompts data pack from Encoded spech files ")
    print("    -o                    : Overwrite existing files")
    print("    -g=gain               : Audio level gain adjust in db.  Default is 0, but can be negative or positive numbers")
    print("    -t=tempo              : Audio tempo (from 0.5 to 2).  Default is {}".format(atempo))
    print("    -r                    : Remove silence from beginning of audio files")
    print("")


def main():
    global overwrite
    global gain
    global atempo
    global removeSilenceAtStart, forceTTSMP3Usage

    fileName   = ""#wordlist_english.csv"
    outputName = ""#voiceprompts.bin"
    voiceName = ""#Matthew or Nicole etc
    configName = ""

    # Command line argument parsing
    try:
        ##opts, args = getopt.getopt(sys.argv[1:], "hof:n:seb:d:c:g:Tt:")
        opts, args = getopt.getopt(sys.argv[1:], "hof:eb:d:c:g:Tt:")
    except getopt.GetoptError as err:
        print(str(err))
        usage("")
        sys.exit(2)

    if os.name == 'nt':
        if (str(shutil.which("ffmpeg.exe")).find("ffmpeg") == -1):
            usage("ERROR: You must install ffmpeg. See https://www.ffmpeg.org/download.html")
            #webbrowser.open("https://www.ffmpeg.org/download.html")
            sys.exit(2)
    elif os.name == 'posix':
        if (str(shutil.which("ffmpeg")).find("ffmpeg") == -1):
            usage("ERROR: You must install ffmpeg. See https://www.ffmpeg.org/download.html")
            #webbrowser.open("https://www.ffmpeg.org/download.html")
            sys.exit(2)

    for opt, arg in opts:
        if opt in ("-h"):
            usage()
            sys.exit(2)
        elif opt in ("-f"):
            fileName = arg
        #elif opt in ("-n"):
        #    voiceName = arg
        elif opt in ("-c"):
            configName = arg
        elif opt in ("-o"):
            overwrite = True
        elif opt in ("-g"):
            gain = arg
        elif opt in ("-r"):
            removeSilenceAtStart = arg
        elif opt in ("-T"):
            forceTTSMP3Usage = True
        elif opt in ('-t'):
            atempo = arg

    if (configName!=""):
        print("Using Config file: {}...".format(configName))

        with open(configName,"r",encoding='utf-8') as csvfile:
            reader = csv.DictReader(filter(lambda row: row[0]!='#', csvfile))
            for row in reader:
                wordlistFilename = row['Wordlist_file'].strip()
                voiceName = row['Voice_name'].strip()
                voicePackName = row['Voice_pack_name'].strip()
                download = row['Download'].strip()
                createPack = row['Createpack'].strip()
                gain = row['Volume_change_db'].strip()
                rs = row['Remove_silence'].strip()
                cfg_atempo = row['Audio_tempo'].strip()
         ## If Audio_tempo is not set, use the default value
                
                if cfg_atempo != '':
                    atempo = cfg_atempo

                ## Add audio tempo value to the filename
                voicePackName = voicePackName.replace('.vpc', '-' + atempo + '.vpc')

                print("Processing " + wordlistFilename+" "+voiceName+" "+voicePackName)

                if not os.path.exists(voiceName):
                    print("Creating folder " + voiceName + " for temporary files")
                    os.mkdir(voiceName)

                if (rs=='y' or rs=='Y'):
                    removeSilenceAtStart = True
                else:
                    removeSilenceAtStart = False

                if (download=='y' or download=='Y'):
                    if not downloadSpeechForWordList(wordlistFilename, voiceName):
                     sys.exit(2)

                        # call buildDataPack
                if (createPack=='y' or createPack=='Y'):
                    buildDataPack(wordlistFilename,voiceName,voicePackName)

        sys.exit(0)


    if (fileName=="" or voiceName==""):
        usage("ERROR: Filename and Voicename must be specified for all operations")
        sys.exit(2)

    if not os.path.exists(voiceName):
        print("Creating folder " + voiceName + " for temporary files")
        os.mkdir(voiceName)

    #for opt, arg in opts:
    #    if opt in ("-s"):
    #        if (downloadSpeechForWordList(fileName,voiceName)==False):
    #            sys.exit(2)

    for opt, arg in opts:
        if opt in ("-b"):
            outputName = arg
            buildDataPack(fileName,voiceName,outputName)

main()
sys.exit(0)
