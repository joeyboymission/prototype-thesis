import os
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from bson import ObjectId
import time

# MongoDB Setup
MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"

def print_status(message, status="INFO"):
    """Print formatted status message with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_colors = {
        "INFO": "\033[94m",  # Blue
        "SUCCESS": "\033[92m",  # Green
        "WARNING": "\033[93m",  # Yellow
        "ERROR": "\033[91m",  # Red
    }
    color = status_colors.get(status, "\033[0m")  # Default to no color
    reset = "\033[0m"
    print(f"{color}[{timestamp}] [{status}] {message}{reset}")

def check_db_connection():
    """Test MongoDB connection and return status"""
    try:
        print_status("Attempting to connect to MongoDB...")
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        client.admin.command('ping')
        print_status("Successfully connected to MongoDB", "SUCCESS")
        return True, client
    except Exception as e:
        print_status(f"Database Error: {e}", "ERROR")
        return False, None

def get_collection_stats(db, collection_name):
    """Get detailed statistics for a collection"""
    try:
        # Get collection stats using collStats command
        stats = db.command("collStats", collection_name)
        
        # Get document count
        doc_count = db[collection_name].count_documents({})
        
        # Get first and last document timestamps
        first_doc = db[collection_name].find_one(sort=[("timestamp", 1)])
        last_doc = db[collection_name].find_one(sort=[("timestamp", -1)])
        
        # Get unique timestamps count
        unique_timestamps = len(db[collection_name].distinct("timestamp"))
        
        # Get index information
        indexes = db[collection_name].list_indexes()
        index_info = []
        for idx in indexes:
            index_info.append({
                "name": idx["name"],
                "keys": idx["key"],
                "unique": idx.get("unique", False)
            })
        
        return {
            "name": collection_name,
            "document_count": doc_count,
            "storage_size": stats.get("size", 0),
            "index_size": stats.get("totalIndexSize", 0),
            "first_timestamp": first_doc.get("timestamp") if first_doc else None,
            "last_timestamp": last_doc.get("timestamp") if last_doc else None,
            "unique_timestamps": unique_timestamps,
            "indexes": index_info,
            "avg_doc_size": stats.get("avgObjSize", 0),
            "num_indexes": stats.get("nindexes", 0)
        }
    except Exception as e:
        print_status(f"Error getting stats for {collection_name}: {e}", "ERROR")
        return None

def analyze_collection_data(collection):
    """Analyze the data structure of a collection"""
    try:
        # Get a sample document
        sample_doc = collection.find_one()
        if not sample_doc:
            return None
        
        # Analyze the structure
        structure = {
            "fields": list(sample_doc.keys()),
            "nested_fields": {},
            "data_types": {}
        }
        
        # Check for nested structures and data types
        for key, value in sample_doc.items():
            structure["data_types"][key] = type(value).__name__
            if isinstance(value, dict):
                structure["nested_fields"][key] = {
                    "fields": list(value.keys()),
                    "types": {k: type(v).__name__ for k, v in value.items()}
                }
        
        return structure
    except Exception as e:
        print_status(f"Error analyzing {collection.name}: {e}", "ERROR")
        return None

def format_size(size_bytes):
    """Format size in bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"

def check_database_status():
    """Check the status of the database and all collections"""
    print_status("="*50)
    print_status("Database Status Check")
    print_status("="*50)
    
    # Check database connection
    db_status, client = check_db_connection()
    if not db_status:
        print_status("Cannot connect to database. Exiting...", "ERROR")
        return
    
    try:
        db = client["Smart_Cubicle"]
        collections = {
            'dispenser_resource': 'Dispenser Module',
            'odor_module': 'Odor Module',
            'occupancy': 'Occupancy Module'
        }
        
        # Get database stats
        db_stats = db.command("dbStats")
        print_status("\nDatabase Overview:")
        print_status(f"Database Name: Smart_Cubicle")
        print_status(f"Total Storage Size: {format_size(db_stats['storageSize'])}")
        print_status(f"Total Data Size: {format_size(db_stats['dataSize'])}")
        print_status(f"Total Index Size: {format_size(db_stats['indexSize'])}")
        print_status(f"Total Collections: {len(collections)}")
        print_status(f"Total Objects: {db_stats['objects']:,}")
        print_status(f"Average Object Size: {format_size(db_stats['avgObjSize'])}")
        
        # Check each collection
        for collection_name, display_name in collections.items():
            print_status(f"\n{'-'*50}")
            print_status(f"Collection: {display_name} ({collection_name})")
            print_status(f"{'-'*50}")
            
            stats = get_collection_stats(db, collection_name)
            
            if stats:
                print_status(f"Document Count: {stats['document_count']:,}")
                print_status(f"Storage Size: {format_size(stats['storage_size'])}")
                print_status(f"Index Size: {format_size(stats['index_size'])}")
                print_status(f"Average Document Size: {format_size(stats['avg_doc_size'])}")
                print_status(f"First Record: {stats['first_timestamp']}")
                print_status(f"Last Record: {stats['last_timestamp']}")
                print_status(f"Unique Timestamps: {stats['unique_timestamps']:,}")
                print_status(f"Number of Indexes: {stats['num_indexes']}")
                
                if stats['indexes']:
                    print_status("\nIndexes:")
                    for idx in stats['indexes']:
                        print_status(f"  - {idx['name']}: {idx['keys']} {'(unique)' if idx['unique'] else ''}")
                
                # Analyze data structure
                structure = analyze_collection_data(db[collection_name])
                if structure:
                    print_status("\nData Structure:")
                    print_status("Fields and Types:")
                    for field, type_name in structure['data_types'].items():
                        print_status(f"  - {field}: {type_name}")
                    
                    if structure['nested_fields']:
                        print_status("\nNested Fields:")
                        for parent, info in structure['nested_fields'].items():
                            print_status(f"  {parent}:")
                            for field, type_name in info['types'].items():
                                print_status(f"    - {field}: {type_name}")
            
            print_status(f"{'-'*50}")
        
    except Exception as e:
        print_status(f"Error during status check: {e}", "ERROR")
    finally:
        client.close()
        print_status("\nStatus check completed!", "SUCCESS")

if __name__ == '__main__':
    check_database_status()
