import sqlite3

conn = sqlite3.connect("database.db")
c = conn.cursor()

new_password = "chatbot@777"  

c.execute("UPDATE admins SET password=? WHERE username=?", (new_password, "admin"))

conn.commit()
conn.close()

print("✅ Password changed successfully!")
