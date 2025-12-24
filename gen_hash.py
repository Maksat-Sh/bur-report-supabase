from passlib.context import CryptContext

pwd = CryptContext(schemes=["pbkdf2_sha256"])
print(pwd.hash("1234"))
