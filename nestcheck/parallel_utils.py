#!/usr/bin/env python
"""
Parallel wrapper functions using the concurrent.futures module.
"""

import warnings
import concurrent.futures
import functools
import tqdm


def parallel_map(func, *arg_iterable, chunksize=1, **kwargs):
    """
    Apply function to iterable with parallel map, and hence returns
    results in order. functools.partial is used to freeze func_pre_args and
    func_kwargs, meaning that the iterable argument must be the last positional
    argument.

    Roughly equivalent to

    [func(*func_pre_args, x, **func_kwargs) for x in arg_iterable]

    Parameters
    ----------
    func: function
        Function to apply to list of args.
    arg_iterable: iterable
        argument to iterate over.
    chunksize: int, optional
        Perform function in batches
    func_pre_args: tuple, optional
        Positional arguments to place before the iterable argument in func.
    func_kwargs: dict, optional
        Additional keyword argumnets for func.
    parallel: bool, optional
        To turn off parallelisation if needed.
    max_workers: int or None, optional
        Number of processes.
        If max_workers is None then concurrent.futures.ProcessPoolExecutor
        defaults to using the number of processors of the machine.
        N.B. If max_workers=None and running on supercomputer clusters with
        multiple nodes, this may default to the number of processors on a
        single node.
    Returns
    -------
    results_list: list of function outputs
    """
    func_pre_args = kwargs.pop('func_pre_args', ())
    func_kwargs = kwargs.pop('func_kwargs', {})
    max_workers = kwargs.pop('max_workers', None)
    parallel = kwargs.pop('parallel', True)
    if kwargs:
        raise TypeError('Unexpected **kwargs: {0}'.format(kwargs))
    func_to_map = functools.partial(func, *func_pre_args, **func_kwargs)
    if parallel:
        pool = concurrent.futures.ProcessPoolExecutor(max_workers=max_workers)
        return list(pool.map(func_to_map, *arg_iterable, chunksize=chunksize))
    else:
        warnings.warn(('parallel_map has parallel=False - turn on '
                       'parallelisation for faster processing'), UserWarning)
        return list(map(func_to_map, *arg_iterable))


def parallel_apply(func, arg_iterable, **kwargs):
    """
    Apply function to iterable with paralleisation and a tqdm progress bar.

    Roughly equivalent to

    [func(*func_pre_args, x, *func_args, **func_kwargs) for x in arg_iterable]

    but will *not* return results in input order.

    Parameters
    ----------
    func: function
        Function to apply to list of args.
    arg_iterable: iterable
        argument to iterate over.
    func_args: tuple, optional
        Additional positional arguments for func.
    func_pre_args: tuple, optional
        Positional arguments to place before the iterable argument in func.
    func_kwargs: dict, optional
        Additional keyword argumnets for func.
    parallel: bool, optional
        To turn off parallelisation if needed.
    max_workers: int or None, optional
        Number of processes.
        If max_workers is None then concurrent.futures.ProcessPoolExecutor
        defaults to using the number of processors of the machine.
        N.B. If max_workers=None and running on supercomputer clusters with
        multiple nodes, this may default to the number of processors on a
        single node.
    Returns
    -------
    results_list: list of function outputs
    """
    max_workers = kwargs.pop('max_workers', None)
    parallel = kwargs.pop('parallel', True)
    func_args = kwargs.pop('func_args', ())
    func_pre_args = kwargs.pop('func_pre_args', ())
    func_kwargs = kwargs.pop('func_kwargs', {})
    tqdm_kwargs = kwargs.pop('tqdm_kwargs', {})
    if kwargs:
        raise TypeError('Unexpected **kwargs: {0}'.format(kwargs))
    if 'leave' not in tqdm_kwargs:  # default to leave=False
        tqdm_kwargs['leave'] = False
    assert isinstance(func_args, tuple), (
        str(func_args) + ' is type ' + str(type(func_args)))
    assert isinstance(func_pre_args, tuple), (
        str(func_pre_args) + ' is type ' + str(type(func_pre_args)))
    # If running in a jupyter notebook then use tqdm_notebook. Otherwise use
    # regular tqdm progress bar
    try:
        progress = tqdm.tqdm_notebook
        assert get_ipython().has_trait('kernel')
    except (NameError, AssertionError):
        progress = tqdm.tqdm
    if not parallel:
        warnings.warn(('parallel_apply has parallel=False - turn on '
                       'parallelisation for faster processing'), UserWarning)
        return [func(*func_pre_args, x, *func_args, **func_kwargs) for x in
                progress(arg_iterable, **tqdm_kwargs)]
    else:
        pool = concurrent.futures.ProcessPoolExecutor(max_workers=max_workers)
        futures = []
        for element in arg_iterable:
            futures.append(pool.submit(func, *func_pre_args, element,
                                       *func_args, **func_kwargs))
        results = []
        for fut in progress(concurrent.futures.as_completed(futures),
                            total=len(arg_iterable), **tqdm_kwargs):
            results.append(fut.result())
        return results
        # # Progress bar for completion of tasks
        # for _ in progress(concurrent.futures.as_completed(futures),
        #                   desc=tqdm_desc, leave=tqdm_leave,
        #                   disable=tqdm_disable, total=len(arg_iterable)):
        #     pass
        # # Use concurrent.futures.wait to return results
        # completed_futures = concurrent.futures.wait(futures)[0]
        # assert len(completed_futures) == len(arg_iterable)
        # return [fut.result() for fut in completed_futures]
