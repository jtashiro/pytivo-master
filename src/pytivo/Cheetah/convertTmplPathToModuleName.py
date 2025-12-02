import os.path
import string

l = ['_'] * 256
for c in string.digits + string.ascii_letters:
    l[ord(c)] = c
_pathNameTransChars = ''.join(l)
del l, c

# Build translation table for Python 3
_trans_table = str.maketrans('', '', ''.join(chr(i) for i in range(256) if chr(i) not in string.digits + string.ascii_letters + '_'))

def convertTmplPathToModuleName(tmplPath,
                                _pathNameTransChars=_pathNameTransChars,
                                splitdrive=os.path.splitdrive,
                                ):
    # Python 3: use str.translate with translation table
    return splitdrive(tmplPath)[1].translate(_trans_table)
