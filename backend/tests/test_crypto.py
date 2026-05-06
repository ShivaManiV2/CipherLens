from backend.core.crypto import (
    generate_rsa_keypair,
    sign_document,
    verify_signature,
    get_file_hash,
    encrypt_private_key,
    decrypt_private_key
)

def test_rsa_keypair_generation():
    priv, pub = generate_rsa_keypair(1024)  # 1024 for faster tests
    assert "BEGIN RSA PRIVATE KEY" in priv
    assert "BEGIN PUBLIC KEY" in pub

def test_sign_and_verify():
    priv, pub = generate_rsa_keypair(1024)
    file_data = b"Hello, secure world!"
    
    signature = sign_document(file_data, priv)
    assert signature is not None
    
    is_valid = verify_signature(file_data, signature, pub)
    assert is_valid is True
    
    # Tampered data
    is_valid_tampered = verify_signature(b"Hello, hacked world!", signature, pub)
    assert is_valid_tampered is False

def test_symmetric_encryption():
    master_key = b"0123456789abcdef0123456789abcdef" # 32 bytes
    priv, _ = generate_rsa_keypair(1024)
    
    encrypted = encrypt_private_key(priv, master_key)
    assert encrypted != priv
    
    decrypted = decrypt_private_key(encrypted, master_key)
    assert decrypted == priv
    
def test_symmetric_encryption_wrong_key():
    master_key = b"0123456789abcdef0123456789abcdef"
    wrong_key = b"abcdef0123456789abcdef0123456789"
    priv, _ = generate_rsa_keypair(1024)
    
    encrypted = encrypt_private_key(priv, master_key)
    
    try:
        decrypt_private_key(encrypted, wrong_key)
        assert False, "Should have raised ValueError"
    except ValueError:
        assert True
