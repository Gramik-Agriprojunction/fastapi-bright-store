import os

# Pytest must not read or write the Gramik CRM database.
os.environ["COLLECTION_BACKEND"] = "memory"
