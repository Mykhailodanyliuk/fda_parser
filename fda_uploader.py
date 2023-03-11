import datetime
import json
import shutil
import time

from zipfile import ZipFile
import os
import ijson
import pymongo
import requests
import wget

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/109.0",
    "Accept": "*/*",
    "Accept-Language": "uk-UA,uk;q=0.8,en-US;q=0.5,en;q=0.3",
    "Accept-Encoding": "gzip, deflate, br"
}


def get_collection_from_db(data_base, collection, client):
    db = client[data_base]
    return db[collection]


def get_json_from_request(url):
    try:
        return json.loads((requests.get(url, headers=headers)).text)
    except:
        time.sleep(10)
        get_json_from_request(url)


def upload_data_to_db(file, collection):
    data_collection = get_collection_from_db('db', collection, client)
    with open(file, 'r', encoding='utf-8') as opened_file:
        for result in ijson.items(opened_file, 'results.item'):
            result['upload_at'] = datetime.datetime.now()
            try:
                data_collection.insert_one(result)
            except:
                'Not added'


def delete_directory(path_to_directory):
    if os.path.exists(path_to_directory):
        shutil.rmtree(path_to_directory)
    else:
        print("Directory does not exist")


def create_directory(path_to_dir, name):
    mypath = f'{path_to_dir}/{name}'
    if not os.path.isdir(mypath):
        os.makedirs(mypath)


def get_fda_list_new_zip_files():
    update_collection = get_collection_from_db('db', 'update_collection', client)
    fda_all_zip = get_collection_from_db('db', 'fda_files', client)
    all_files_json = get_json_from_request('https://api.fda.gov/download.json')
    files_list = []
    for category in all_files_json.get('results').keys():
        for subcategory in all_files_json.get('results').get(category).keys():
            if subcategory != 'drugsfda':
                for partition in all_files_json.get('results').get(category).get(subcategory).get('partitions'):
                    file_link = partition.get('file')
                    if not fda_all_zip.find_one({'zip_name': file_link}):
                        files_list.append({'category': category, 'subcategory': subcategory, 'file_link': file_link})
    if not files_list:
        for category in all_files_json.get('results').keys():
            for subcategory in all_files_json.get('results').get(category).keys():
                if subcategory != 'drugsfda':
                    update_query = {'name': f'fda_{category}_{subcategory}',
                                    'new_records': 0,
                                    'total_records': get_collection_from_db('db',
                                                                            f'fda_{category}_{subcategory}',
                                                                            client).estimated_document_count(),
                                    'update_date': datetime.datetime.now()}
                    update_collection.update_one({'name': f'fda_{category}_{subcategory}'}, {"$set": update_query})
    return files_list


def upload_fda_data(file_dict):
    update_collection = get_collection_from_db('db', 'update_collection', client)
    fda_all_zip = get_collection_from_db('db', 'fda_files', client)
    file_link = file_dict.get('file_link')
    category = file_dict.get('category')
    subcategory = file_dict.get('subcategory')
    collection = get_collection_from_db('db', f'fda_{category}_{subcategory}', client)
    last_len_records = collection.estimated_document_count()
    current_directory = os.getcwd()
    directory_name = 'fda'
    path_to_directory = f'{current_directory}/{directory_name}'
    delete_directory(path_to_directory)
    create_directory(current_directory, directory_name)
    zip_file_path = file_link[::-1]
    zip_file_path = f"{path_to_directory}/{zip_file_path[:zip_file_path.find('/')][::-1]}"
    wget.download(file_link, zip_file_path)
    with ZipFile(zip_file_path, 'r') as zip:
        zip.extractall(path=path_to_directory)
    file_path = zip_file_path.replace('.zip', '')
    upload_data_to_db(file_path, f'fda_{category}_{subcategory}')
    delete_directory(path_to_directory)
    fda_all_zip.insert_one({'zip_name': file_link})

    total_records = collection.estimated_document_count()
    update_query = {'name': f'fda_{category}_{subcategory}', 'new_records': total_records - last_len_records,
                    'total_records': total_records,
                    'update_date': datetime.datetime.now()}
    if update_collection.find_one({'name': f'fda_{category}_{subcategory}'}):
        update_collection.update_one({'name': f'fda_{category}_{subcategory}'}, {"$set": update_query})
    else:
        update_collection.insert_one(update_query)


if __name__ == '__main__':
    while True:
        client = pymongo.MongoClient('mongodb://localhost:27017')
        for zip_file in get_fda_list_new_zip_files():
            print(zip_file)
            upload_fda_data(zip_file)
        client.close()
