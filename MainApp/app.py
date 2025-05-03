from flask import Flask, render_template, send_from_directory, request, url_for, redirect
from constants import FLASK_SECRET_KEY, FERNET_ID_KEY
from pymongo import MongoClient
import gridfs
import bson
from cryptography.fernet import Fernet,  InvalidToken



##### mongo
client = MongoClient("mongodb://localhost:27017/")
db = client["scripts"]
fs = gridfs.GridFS(db)
metadata_collection = db["file_metadata"] 

##### MAKE EVERYTHING AVAILABLE OFFLINE
app = Flask(__name__)
app.config['SECRET_KEY'] = FLASK_SECRET_KEY
#########################################


def save_file(content, keyword, language, index):
    file_id = fs.put(content.encode(), filename=keyword) #grid fs

    metadata_collection.insert_one({ #metadata diff collection
        "_id": file_id, 
        "keyword": keyword,
        "language": language, 
        "index": index
    })
    
    #print(f"File stored with ID {file_id} and keyword {keyword}")

def list_files():
    files = list(metadata_collection.find())
    file_id_enc = Fernet(FERNET_ID_KEY)
    for file in files:
        file["content"] = fs.get(file['_id']).read().decode().replace("\xa0", " ")
        file['_id'] = file_id_enc.encrypt(str(file['_id']).encode()).decode()
    return files

def update_file(file_id, new_text, keyword, language):
    file_id = bson.objectid.ObjectId(file_id)
    file_entry = metadata_collection.find_one({"_id": file_id})
    ind = file_entry["index"]
    if not file_entry:
        return [1, "No file found for this keyword."]

    fs.delete(file_id)
    new_file_id = fs.put(new_text.encode(), filename=keyword)

    metadata_collection.delete_one({"_id": file_entry["_id"]})
    metadata_collection.insert_one({
        "_id": new_file_id,  
        "keyword": keyword,
        "language": language,
        "index":ind
    })
    return [0, new_file_id]

def delete_file(file_id): 
    file_id = bson.objectid.ObjectId(file_id)   
    file_entry = metadata_collection.find_one({"_id": file_id})
    if not file_entry:
        return [1, "File not found"]
    
    try:
        fs.delete(file_id)
        
        metadata_collection.delete_one({"_id": file_id})
    except Exception as e:
        return [1, f"Deletion failed: {str(e)}"]
    
    return [0, "File deleted successfully"]

@app.route('/', methods=['POST', 'GET'])
def real_ind():
    files = list_files()
    files = sorted(files, key=lambda x: x['keyword'])
    if request.method == "POST":
        data = request.form
        #print(data)
        file_id_dec = Fernet(FERNET_ID_KEY)
        if(data['type']=='Save'):
            if(data['index']!=''):
                file_id = file_id_dec.decrypt(data['index'].encode()).decode()
                existing = update_file(file_id, data['editor_content'], data['keyword'], data['language'])
                if(existing[0] == 1):
                    save_file(data['editor_content'], data['keyword'], data['language'], len(files))
            else:
                save_file(data['editor_content'], data['keyword'], data['language'], len(files))
            return redirect(url_for('real_ind'))
        elif(data['type'] == 'Delete' and data['index']!=''):
            file_id = file_id_dec.decrypt(data['index'].encode()).decode()
            #print(file_id)
            delete_file(file_id=file_id)
            return redirect(url_for('real_ind'))
    return render_template('index.html', files=files)

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=False)
