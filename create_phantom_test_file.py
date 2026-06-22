def create_phantom_test_file(file_path: str, contents: str) -> None:
    """
    Creates a new file at the specified path with the given contents.
    
    Args:
    - file_path (str): The path where the file should be created.
    - contents (str): The text to be written into the file.
    """
    try:
        with open(file_path, 'w') as file:
            file.write(contents)
    except PermissionError:
        print(f"Permission denied: Unable to create file at {file_path}")
    except OSError as e:
        print(f"Error creating file: {e}")

# Create the phantom_test.txt file
create_phantom_test_file('phantom_test.txt', 'Hello from PhantomDev!')