from PIL import Image
import sys

def check_transparency(img_path):
    img = Image.open(img_path)
    if img.mode != 'RGBA':
        print(f"Mode is {img.mode}, not RGBA")
        return
    
    datas = img.getdata()
    transparent_count = 0
    for item in datas:
        if item[3] == 0:
            transparent_count += 1
    
    print(f"Total pixels: {len(datas)}")
    print(f"Transparent pixels: {transparent_count}")

if __name__ == "__main__":
    check_transparency(sys.argv[1])
