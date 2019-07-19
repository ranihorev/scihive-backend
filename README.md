# SciHive 

Read, collaborate and talk about scientific papers

# Set Up

### Prerequisites 
- You will need both python and pip on your machine to run the back-end code.  
To install pip for python3 execute the following:  
`sudo apt-get install python3-pip`

*It is reccommended to use a virtual environment when installing the various necessary modules.*  
You can obtain virtualenv with a simple pip3 install.
To start your virtual environment run the following code in the terminal:  
```python
cd scihive-backend
source venv/bin/activate
```
To deactivate the environment, type `deactivate`.  
If you're having issues more information can be found [here](https://docs.python-guide.org/dev/virtualenvs/).

- Once you have a virtual environment established, run the following command:
`pip3 install -r requirements.txt`  
This retrieves and installs all the required modules at once. 

- This website uses data from Twitter to measure the popularity of certain papers. Thus you will need access to Twitter's [developer API](https://docs.inboundnow.com/guide/create-twitter-application/).  
Your Twitter API key and secret key can be placed in an .env file as demonstrated in the example.

- Next, make sure MongoDB is installed and running. Of course, the installation process will depend on your OS.  
Then execute "single-background-tasks-run.py". This will gather data from the Arxiv website and store it in the database. 

- Now all that is left to do is to run `python3 serve.py`.  
**You will need the back-end to be running in order to host the website locally!**

### Notes
- Please install pandoc to support references extraction from [here](https://pandoc.org/installing.html)
- Please install pdftotext to support acronyms extraction: `sudo apt-get install poppler-utils`
- You may need to install the natural language processing module, spaCy:  
```python
pip3 install spacy 
python3 -m spacy download en_core_web_sm
``` 

### Changelog

- May 31, 2019 - Acronym extraction and enrichment (from other papers)
