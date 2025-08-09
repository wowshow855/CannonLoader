# Redcon WEBP file extraction code by wowshowman
import os

#print("Redcon WEBP file extraction code by wowshowman. (tx.pk is the texture file.)")
def extract_webp_images(pk_file, output_dir):
    with open(pk_file, "rb") as f:
        data = f.read()

    os.makedirs(output_dir, exist_ok=True)

    index = 0
    count = 0
    while index < len(data):
        # Look for "RIFF"
        if data[index:index+4] == b'RIFF' and data[index+8:index+12] == b'WEBP':
            # Get size field (4 bytes little endian, not including first 8 bytes)
            size = int.from_bytes(data[index+4:index+8], "little")
            total_size = size + 8  # Add RIFF header

            webp_data = data[index:index+total_size]
            output_path = os.path.join(output_dir, f"image_{count:03}.webp")
            with open(output_path, "wb") as out_f:
                out_f.write(webp_data)

            print(f"Extracted: {output_path}")
            index += total_size
            count += 1
        else:
            index += 1

    if count == 0:
        print("No WEBP images found.")
    else:
        print(f"Done! {count} images extracted.")

#tx_path = input("Please specify .pk filepath. ")
#output_path = input("Please specify output folder name. ")
#extract_webp_images(tx_path, output_path)
