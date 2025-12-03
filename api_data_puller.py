"""
Docstring for api_data_puller

"""

import sqlite3

# Connect to DB
db_p = 'weather.db'
conn = sqlite3.connect(db_p)
cursor = conn.cursor()

# Close connection to DB
conn.close()




def main():
    pass

if __name__ == '__main__': main()