""" common utilities used by automol
"""

# functions
from automol.util._util import equivalence_partition
from automol.util._util import value_similar_to
from automol.util._util import scale_iterable
# submodules
from automol.util import vec
from automol.util import mat
from automol.util import dict_


__all__ = [
    # functions
    'equivalence_partition',
    'value_similar_to',
    'scale_iterable',
    # submodules
    'vec',
    'mat',
    'dict_'
]