# textbook-match
Developed by Carl Hunt. Textbooks Match is a process that takes data from Follett (in the form of a report in the form of an Excel file) and indexes it into Elasticsearch to find matches in Primo VE.

# textbooks-match

This repo contains code to run the textbooks match process.

## Set up
Create and activate the virtual environment:

    virtualenv .venv
    source .venv/bin/activate

Install requirements:
    
    pip install -r requirements.txt

## Adding packages
If you add any packages ("pip install my-package") update requirements.txt:

    pip freeze > requirements.txt
