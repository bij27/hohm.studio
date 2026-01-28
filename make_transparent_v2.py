from PIL import Image, ImageChops
import sys

def make_transparent_better(img_path, output_path):
    img = Image.open(img_path).convert("RGBA")
    
    # Create a mask for "white-ish" pixels
    # We'll consider anything with high R, G, B as background
    data = img.getdata()
    new_data = []
    
    for item in data:
        # If R, G, B are all > 230, it's likely background
        if item[0] > 230 and item[1] > 230 and item[2] > 230:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)
            
    img.putdata(new_data)
    
    # Trim empty space around the symbol to make it even more prominent
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
        
    img.save(output_path, "PNG")

if __name__ == "__main__":
    make_transparent_better(sys.argv[1], sys.argv[2])
