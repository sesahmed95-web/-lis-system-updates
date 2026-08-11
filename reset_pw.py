import sqlite3, hashlib
c = sqlite3.connect("lis.db")
c.execute("UPDATE designer_account SET username=?, password_hash=? WHERE id=1", ("designer", hashlib.sha256("Temp12345".encode()).hexdigest()))
c.commit()
print("done")
