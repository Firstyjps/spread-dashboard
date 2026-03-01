import asyncio
import lighter
import eth_account

L1_PRIVATE_KEY = "YOUR_L1_MASTER_KEY_HERE"
ACCOUNT_INDEX = "YOUR_ACCOUNT_INDEX_HERE"
API_KEY_INDEX = 3
BASE_URL = "https://mainnet.zklighter.elliot.ai"

async def main():
    l2_private_key, l2_public_key, err = lighter.create_api_key()
    if err: raise Exception(err)

    client = lighter.ApiClient(lighter.Configuration(host=BASE_URL))
    signer = lighter.SignerClient(
        url=BASE_URL,
        account_index=ACCOUNT_INDEX,
        api_private_keys={API_KEY_INDEX: l2_private_key}
    )

    print(f"--- 🚀 กำลังลงทะเบียน API Key บน Lighter ---")
    
    _, err = await signer.change_api_key(
        eth_private_key=L1_PRIVATE_KEY,
        new_pubkey=l2_public_key,
        api_key_index=API_KEY_INDEX
    )
    
    if err:
        print(f"❌ ลงทะเบียนไม่สำเร็จ: {err}")
    else:
        print(f"✅ ลงทะเบียนสำเร็จ!")
        print(f"\nให้นำค่านี้ไปใส่ในไฟล์ .env ของคุณ:")
        print(f"LIGHTER_PRIVATE_KEY={l2_private_key}")
        print(f"LIGHTER_API_KEY_INDEX={API_KEY_INDEX}")
        print(f"\n⚠️ เก็บรักษา L2 Private Key นี้ไว้ให้ดี (มันคือรหัสเทรดของคุณ)")

    await signer.api_client.close()

if __name__ == "__main__":
    asyncio.run(main())