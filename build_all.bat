rem need to ensure vpcgen\scripts\c2enc.exe is in your path. 
cd languages\english_uk
py ..\..\OpenRTXVoicePromptsBuilder.py -c config.csv
py ..\..\OpenRTXVoicePromptsBuilder.py -c config_1.5.csv

cd ..\english_usa
py ..\..\OpenRTXVoicePromptsBuilder.py -c config.csv
py ..\..\OpenRTXVoicePromptsBuilder.py -c config_1.5.csv

cd ..\..