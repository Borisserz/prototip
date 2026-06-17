from cryptography.fernet import Fernet

# В реальном приложении этот ключ должен загружаться из переменных окружения
SECRET_ENCRYPTION_KEY = Fernet.generate_key()
cipher_suite = Fernet(SECRET_ENCRYPTION_KEY)

def encrypt_data(data: str) -> str:
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str) -> str:
    return cipher_suite.decrypt(encrypted_data.encode()).decode()
