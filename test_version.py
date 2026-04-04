import asyncio
from pymobiledevice3.lockdown import create_using_usbmux

async def check_version():
    try:
        lockdown = await create_using_usbmux()
        product_version = lockdown.product_version
        print(f"iOS Version: {product_version}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_version())
