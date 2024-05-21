from pymongo import MongoClient
from decouple import config

client = MongoClient(config('ATLAS_URI'))
WhoWillWin_db = client['WhoWillWin']
UFCodds_db = client['UFCodds']