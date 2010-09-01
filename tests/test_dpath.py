from nose import tools

from drivel.components.stats import dpath
from drivel.components.stats import PathError

@tools.raises(PathError)
def test_non_existant_path():
    data = {'foo': 'bar'}
    dpath(data, '/doesnotexit')

def test_lists():
    data = {'foo': ['a', 'b', 'c']}
    assert dpath(data, '/foo/1') == 'b'

def test_basic():
    data = {'foo': {'bar': [1, 2, 3]}}
    assert dpath(data, '/foo/bar') == [1, 2, 3]

@tools.raises(PathError)
def test_string_in_path():
    data = {'foo': "hello world"}
    dpath(data, '/foo/3')
