import os
import stat


def multi_linked_files(root):
    root = os.path.abspath(root)
    try:
        info = os.lstat(root)
    except FileNotFoundError as err:
        raise ValueError('scan root must be a directory') from err
    if (not stat.S_ISDIR(info.st_mode)
            or getattr(info, 'st_file_attributes', 0) & 0x400):
        raise ValueError('scan root must be a directory without aliases')
    found = []
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                info = os.lstat(entry.path)
                if (stat.S_ISLNK(info.st_mode)
                        or getattr(info, 'st_file_attributes', 0) & 0x400):
                    continue
                if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
                    found.append(os.path.relpath(entry.path, root).replace(os.sep, '/'))
                elif stat.S_ISDIR(info.st_mode):
                    pending.append(entry.path)
    return sorted(found)


def check_grants(roots, error):
    for root in roots:
        try:
            linked = multi_linked_files(root)
        except (OSError, ValueError) as err:
            raise error('hardlink scan failed; grant refused') from err
        if linked:
            raise error('multiple links in grant (a second name): %s' % linked[0])
