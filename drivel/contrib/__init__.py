def username_from_path(path, part=0):
    return path.strip('/').split('/')[part]

