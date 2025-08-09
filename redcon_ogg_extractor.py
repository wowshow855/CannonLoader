# Redcon Ogg file extraction code by wowshowman
import os

def extract_ogg_files(file_path, output_path, verbose=True):
    if verbose:
        print("Redcon Ogg file extraction code by wowshowman. (sm.pk and sx.pk are the audio file.)")
    
    # Check if input file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Input file not found: {file_path}")
    
    # Read the input file
    try:
        with open(file_path, "rb") as f:
            data = f.read()
    except IOError as e:
        raise IOError(f"Error reading file {file_path}: {e}")
    
    # Create output directory
    try:
        os.makedirs(output_path, exist_ok=True)
    except OSError as e:
        raise IOError(f"Error creating output directory {output_path}: {e}")
    
    ogg_signature = b"OggS"
    ogg_files = []
    cursor = 0
    file_index = 0
    data_len = len(data)
    
    while cursor < data_len:
        start = data.find(ogg_signature, cursor)
        if start == -1:
            break
        
        pages = []
        while start != -1:
            if start + 27 > data_len:
                break
            
            header_type_flag = data[start + 5]
            segment_count = data[start + 26]
            
            segment_table_end = start + 27 + segment_count
            if segment_table_end > data_len:
                break
            
            segment_sizes = data[start + 27:segment_table_end]
            page_data_size = sum(segment_sizes)
            page_full_size = 27 + segment_count + page_data_size
            
            end = start + page_full_size
            if end > data_len:
                break
            
            pages.append(data[start:end])
            cursor = end
            
            if header_type_flag & 0x04:
                break
            
            start = data.find(ogg_signature, cursor)
        
        if pages:
            ogg_data = b''.join(pages)
            filename = f"{file_index:04}.ogg"
            try:
                with open(os.path.join(output_path, filename), "wb") as f:
                    f.write(ogg_data)
                ogg_files.append(filename)
                file_index += 1
                if verbose:
                    print(f"Extracting file: {filename}")
            except IOError as e:
                if verbose:
                    print(f"Error writing file {filename}: {e}")
                continue
    
    if verbose:
        print(f"Extraction successful! Extracted {len(ogg_files)} files.")
    
    return ogg_files, len(ogg_files)

#file_path = input("Please specify the .pk filepath: ")
#output_path = input("Please specify output folder name: ")
#extract_ogg_files(file_path, output_path)