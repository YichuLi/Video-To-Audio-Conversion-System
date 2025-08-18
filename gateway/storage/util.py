import pika, json
import traceback # Import the traceback module

def upload(f, fs, channel, access):
    fid = None # Initialize fid to None

    # put the file in the mongo database
    try:
        print("Attempting fs.put(f)...")
        fid = fs.put(f)
        print(f"Successfully put file to GridFS, fid: {fid}")
    except Exception as err:
        print("Error during MongoDB put:")
        print(f"Error type: {type(err)}") # Print the error type
        traceback.print_exc() # Print the full traceback
        return "internal server error during storage", 500 # More specific error message

    message = {
        "video_fid": str(fid),
        "mp3_fid": None,
        "username": access["username"],
    }

    # Publish message to RabbitMQ
    try:
        print("Attempting channel.basic_publish...")
        channel.basic_publish(
            exchange="",
            routing_key="video",
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE
            ),
        )
        print("Successfully published message to RabbitMQ.")
    except Exception as err:
        print("Error during RabbitMQ publish:")
        print(f"Error type: {type(err)}") # Print the error type
        traceback.print_exc() # Print the full traceback
        # Attempt to delete the file from GridFS if the publish fails
        try:
            if fid: # Only try to delete if fid was successfully obtained
                print(f"Attempting to delete file {fid} from GridFS after publish failure...")
                fs.delete(fid)
                print(f"Successfully deleted file {fid} from GridFS.")
        except Exception as delete_err:
            print(f"Error deleting file {fid} from GridFS after publish failure:")
            print(f"Error type: {type(delete_err)}") # Print delete error type
            traceback.print_exc() # Print traceback for delete error too

        return "internal server error during messaging", 500 # More specific error message

    # If both operations succeed, return None (indicating no error)
    return None
