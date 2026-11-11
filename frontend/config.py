import os

MONGO_URI = os.getenv('MONGO_URI')
MONGO_DB_NAME = os.getenv('MONGO_DB_NAME')
for _yard in ('JACKS', 'LKQ', 'PICKNPULL', 'PULLAPART', 'UPULLANDSAVE', 'TEARAPART', 'UTPAP', 'PULLNSAVE'):
    globals()[f'MONGO_COLLECTION_NAME_{_yard}'] = os.getenv(f'MONGO_COLLECTION_NAME_{_yard}')
