import os, gridfs, pika, json
from flask import Flask, request, send_file
from flask_pymongo import PyMongo
from auth import validate
from auth_svc import access # Assuming this module contains the login function
from storage import util
from bson.objectid import ObjectId
import traceback # Import traceback for detailed error logging
import json # Explicitly import json if not already at the top

server = Flask(__name__)

# Initialize variables to None before attempting connection/initialization
mongo_video = None
mongo_mp3 = None
fs_videos = None
fs_mp3s = None
connection = None
channel = None

# MongoDB connections - Use the Kubernetes Service Name 'mongodb-service'
# The port is the service port (27017)
# Ensure your MongoDB service in Kubernetes is named 'mongodb-service'
try:
    print("Attempting to connect to MongoDB...")
    mongo_video = PyMongo(server, uri="mongodb://mongodb-service:27017/videos")
    mongo_mp3 = PyMongo(server, uri="mongodb://mongodb-service:27017/mp3s")
    # Attempt a quick check to see if MongoDB is reachable
    mongo_video.db.command('ping')
    print("Successfully connected to MongoDB")

    # Initialize GridFS instances ONLY if MongoDB connection was successful
    print("Attempting to initialize GridFS...")
    fs_videos = gridfs.GridFS(mongo_video.db)
    fs_mp3s = gridfs.GridFS(mongo_mp3.db)
    print("Successfully initialized GridFS")

except Exception as e:
    print("Error during MongoDB connection or GridFS initialization:")
    traceback.print_exc()
    # If connection or initialization fails, the variables will remain None or partially initialized.


# RabbitMQ connection - Use the Kubernetes Service Name 'rabbitmq'
# The default RabbitMQ port is 5672, but your service might expose it on a different port.
# Check your rabbit/manifests/service.yaml for the correct port.
# Ensure your RabbitMQ service in Kubernetes is named 'rabbitmq'
try:
    print("Attempting to connect to RabbitMQ...")
    # Use the service name 'rabbitmq' and the correct port (default is 5672)
    connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq")) # Hostname is the service name
    channel = connection.channel()
    print("Successfully connected to RabbitMQ")
except Exception as e:
    print("Error connecting to RabbitMQ:")
    traceback.print_exc()
    # If connection fails, connection and channel will remain None or partially initialized.


@server.route("/login", methods=["POST"])
def login():
    # Assuming access.login handles request and returns token, err
    token, err = access.login(request)

    if not err:
        return token
    else:
        # Assuming err is a tuple like (message, status_code)
        return err


@server.route("/upload", methods=["POST"])
def upload():
    # Explicitly declare globals to ensure we are using the top-level variables
    # This shouldn't be strictly necessary for top-level globals but can help diagnose scope issues.
    global fs_videos
    global channel

    # Check if critical dependencies were initialized during startup
    if fs_videos is None:
        print("Error: fs_videos was not initialized during startup.")
        # Return a 500 error indicating a server-side dependency issue
        return "Internal server error: Storage service not available", 500
    if channel is None:
        print("Error: RabbitMQ channel was not initialized during startup.")
        # Return a 500 error indicating a server-side dependency issue
        return "Internal server error: Messaging service not available", 500


    # 1. Validate the token by calling the auth service
    # Ensure AUTH_SVC_ADDRESS environment variable points to the auth service name and port
    access_response_text, err = validate.token(request)

    if err:
        # If validate.token returned an error tuple, return it directly
        print(f"Token validation failed: {err}")
        return err

    # 2. Parse the JSON response from the auth service
    access_data = None
    try:
        access_data = json.loads(access_response_text)
        print(f"Successfully parsed access data: {access_data}")
    except json.JSONDecodeError as e:
        print("Error decoding JSON response from auth service:")
        print(f"Response text was: {access_response_text}")
        traceback.print_exc()
        return "Invalid response from authentication service", 500
    except Exception as e:
        # Catch any other unexpected errors during JSON parsing
        print("Unexpected error during JSON parsing from auth service:")
        traceback.print_exc()
        return "Internal server error during authentication response processing", 500


    # 3. Check for the 'admin' key in the parsed data
    is_admin = False
    try:
        # Use .get() with default to avoid KeyError if 'admin' is missing
        is_admin = access_data.get("admin", False)
        print(f"Admin status: {is_admin}")
    except Exception as e:
        # Catch any other unexpected errors accessing data
        print("Unexpected error accessing 'admin' key from authentication data:")
        traceback.print_exc()
        return "Internal server error processing authentication data", 500


    # 4. Proceed with upload only if admin
    if is_admin:
        if len(request.files) > 1 or len(request.files) < 1:
            print("Received incorrect number of files.")
            return "exactly 1 file required", 400

        # Assuming the file input field name is 'file'
        if 'file' not in request.files:
             print("No 'file' part in the request.")
             return "No file part in the request", 400

        file_to_upload = request.files['file']

        if file_to_upload.filename == '':
            print("No selected file.")
            return "No selected file", 400


        print(f"Attempting to upload file: {file_to_upload.filename}")
        # Call the utility function to handle storage and messaging
        # util.upload is expected to return None on success, or (message, status_code) on error
        # Pass access_data (the dict) to util.upload
        # The traceback points to this line:
        err_from_util = util.upload(file_to_upload, fs_videos, channel, access_data)

        if err_from_util:
            # If util.upload returned an error, return it
            print(f"Error from util.upload: {err_from_util}")
            return err_from_util

        print("File upload and message publishing successful!")
        return "success!", 200
    else:
        print("User is not authorized for upload.")
        return "not authorized", 401


@server.route("/download", methods=["GET"])
def download():
    # Similar error handling could be added here
    # Explicitly declare globals for download as well
    global fs_mp3s

    # Check if critical dependency was initialized
    if fs_mp3s is None:
        print("Error: fs_mp3s was not initialized during startup.")
        return "Internal server error: Storage service not available", 500


    access_response_text, err = validate.token(request)

    if err:
        return err

    access_data = None
    try:
        access_data = json.loads(access_response_text)
    except Exception as e:
         print("Error decoding JSON response from auth service during download:")
         traceback.print_exc()
         return "Invalid response from authentication service", 500


    if access_data.get("admin", False): # Using .get() for safety
        fid_string = request.args.get("fid")

        if not fid_string:
            return "fid is required", 400

        try:
            # Attempt to get the file from GridFS
            out = fs_mp3s.get(ObjectId(fid_string))
            print(f"Successfully retrieved file {fid_string} from GridFS for download.")
            return send_file(out, download_name=f"{fid_string}.mp3")
        except Exception as err:
            # Catch errors during GridFS get
            print(f"Error retrieving file {fid_string} from GridFS:")
            traceback.print_exc()
            return "internal server error during file retrieval", 500

    print("User is not authorized for download.")
    return "not authorized", 401


if __name__ == "__main__":
    # Running in debug mode can also help see tracebacks directly
    # However, avoid debug mode in production
    server.run(host="0.0.0.0", port=8080, debug=False) # Set debug=True temporarily if needed
