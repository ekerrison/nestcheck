#!/usr/bin/env python
"""
Test the nestcheck module installation.
"""
import os
import shutil
import unittest
import functools
import importlib
import numpy as np
import numpy.testing
import pandas as pd
import pandas.testing
import matplotlib
import scipy.special
import nestcheck.parallel_utils
import nestcheck.io_utils
import nestcheck.estimators as e
import nestcheck.analyse_run as ar
import nestcheck.plots
import nestcheck.data_processing
import nestcheck.diagnostics


TEST_CACHE_DIR = 'cache_tests'
TEST_DIR_EXISTS_MSG = ('Directory ' + TEST_CACHE_DIR + ' exists! Tests use '
                       'this dir to check caching then delete it afterwards, '
                       'so the path should be left empty.')


class TestDataProcessing(unittest.TestCase):

    def setUp(self):
        """Make a directory for saving test results."""
        assert not os.path.exists(TEST_CACHE_DIR), TEST_DIR_EXISTS_MSG

    def tearDown(self):
        """Remove any caches saved by the tests."""
        try:
            shutil.rmtree(TEST_CACHE_DIR)
        except FileNotFoundError:
            pass

    def test_batch_process_data_unexpected_kwarg(self):
        """Test unexpected kwargs checks."""
        self.assertRaises(
            TypeError, nestcheck.data_processing.batch_process_data,
            ['path'], base_dir=TEST_CACHE_DIR, unexpected=1)

    def test_check_ns_run_logls(self):
        """Ensure check_ns_run_logls raises error if and only if
        warn_only=False"""
        repeat_logl_run = {'logl': np.asarray([0, 0, 1])}
        self.assertRaises(
            AssertionError, nestcheck.data_processing.check_ns_run_logls,
            repeat_logl_run, warn_only=False)
        nestcheck.data_processing.check_ns_run_logls(repeat_logl_run, warn_only=True)

    def test_batch_process_data_not_present(self):
        file_root = 'dummy_run'
        dead, run = get_dummy_dead_points()
        nestcheck.data_processing.check_ns_run(run)
        np.savetxt(file_root + '.txt', dead)
        os.makedirs(TEST_CACHE_DIR)
        np.savetxt(TEST_CACHE_DIR + '/' + file_root + '_dead-birth.txt', dead)
        processed_run = nestcheck.data_processing.batch_process_data(
            [file_root, 'an_empty_path'], base_dir=TEST_CACHE_DIR,
            parallel=False)[0]
        nestcheck.data_processing.check_ns_run(processed_run)
        for key in run.keys():
            if key not in ['output']:
                numpy.testing.assert_array_equal(
                    run[key], processed_run[key], err_msg=key + ' not the same')
        self.assertEqual(processed_run['output']['file_root'], file_root)
        self.assertEqual(processed_run['output']['base_dir'], TEST_CACHE_DIR)


class TestIOUtils(unittest.TestCase):

    def setUp(self):
        """Make a directory and data for io testing."""
        assert not os.path.exists(TEST_CACHE_DIR), TEST_DIR_EXISTS_MSG
        self.test_data = np.random.random(10)

        @nestcheck.io_utils.save_load_result
        def save_load_func(data):
            return data
        self.save_load_func = save_load_func

    def tearDown(self):
        """Remove any caches saved by the tests."""
        try:
            shutil.rmtree(TEST_CACHE_DIR)
        except FileNotFoundError:
            pass

    def test_save_load_wrapper(self):
        """Try saving and loading some test data and check it dosnt change."""
        # Without save_name (will neither save nor load)
        data_out = self.save_load_func(self.test_data, save=True, load=True)
        self.assertTrue(np.array_equal(self.test_data, data_out))
        # Before any data saved (will save but not load)
        data_out = self.save_load_func(self.test_data, save=True, load=True,
                                       save_name=TEST_CACHE_DIR + '/io_test')
        self.assertTrue(np.array_equal(self.test_data, data_out))
        # After data saved (will load)
        data_out = self.save_load_func(self.test_data, save=True, load=True,
                                       save_name=TEST_CACHE_DIR + '/io_test')
        self.assertTrue(np.array_equal(self.test_data, data_out))
        # Check handling of permission and memory errors when saving
        nestcheck.io_utils.pickle_save(data_out, '//')

    def test_load_filenotfound(self):
        """Test loading files which dont exist causes FileNotFoundError."""
        self.assertRaises(FileNotFoundError, nestcheck.io_utils.pickle_load,
                          TEST_CACHE_DIR + 'not_here')

    def test_no_overwrite(self):
        """Check option to not overwrite existing files."""
        # Save our test data
        nestcheck.io_utils.pickle_save(self.test_data,
                                       TEST_CACHE_DIR + '/io_test',
                                       print_time=True)
        # Try saving some different data to same path
        nestcheck.io_utils.pickle_save(self.test_data - 100,
                                       TEST_CACHE_DIR + '/io_test',
                                       overwrite_existing=False)
        # Check the test data was not edited
        data_out = nestcheck.io_utils.pickle_load(TEST_CACHE_DIR + '/io_test')
        self.assertTrue(np.array_equal(self.test_data, data_out))

    def test_save_load_unexpected_kwargs(self):
        """Unexpected kwarg should throw exception."""
        self.assertRaises(TypeError, nestcheck.io_utils.pickle_load,
                          self.test_data, TEST_CACHE_DIR + '/io_test',
                          unexpected=1)
        self.assertRaises(TypeError, nestcheck.io_utils.pickle_save,
                          self.test_data, TEST_CACHE_DIR + '/io_test',
                          unexpected=1)


class TestPandasFunctions(unittest.TestCase):

    def setUp(self):
        self.nrows = 100
        self.ncols = 3
        self.data = np.random.random((self.nrows, self.ncols))
        self.col_names = ['samples']
        self.col_names += ['est ' + str(i) for i in range(self.ncols - 1)]
        self.df = pd.DataFrame(self.data, columns=self.col_names)
        self.sum_df = nestcheck.pandas_functions.summary_df(
            self.df, true_values=np.zeros(self.ncols),
            include_true_values=True, include_rmse=True)

    def test_summary_df(self):
        self.assertEqual(self.sum_df.shape, (7, self.ncols))
        numpy.testing.assert_array_equal(
            self.sum_df.loc[('mean', 'value'), :].values,
            np.mean(self.data, axis=0))
        numpy.testing.assert_array_equal(
            self.sum_df.loc[('mean', 'uncertainty'), :].values,
            np.std(self.data, axis=0, ddof=1) / np.sqrt(self.nrows))
        numpy.testing.assert_array_equal(
            self.sum_df.loc[('std', 'value'), :].values,
            np.std(self.data, axis=0, ddof=1))
        numpy.testing.assert_array_equal(
            self.sum_df.loc[('rmse', 'value'), :].values,
            np.sqrt(np.mean(self.data ** 2, axis=0)))
        self.assertRaises(
            TypeError, nestcheck.pandas_functions.summary_df,
            self.df, true_values=np.zeros(self.ncols),
            include_true_values=True, include_rmse=True, unexpected=1)

    def test_summary_df_from_array(self):
        df = nestcheck.pandas_functions.summary_df_from_array(
            self.data, self.col_names, true_values=np.zeros(self.ncols),
            include_true_values=True, include_rmse=True)
        pandas.testing.assert_frame_equal(df, self.sum_df)
        # check axis argument
        df = nestcheck.pandas_functions.summary_df_from_array(
            self.data.T, self.col_names, true_values=np.zeros(self.ncols),
            include_true_values=True, include_rmse=True, axis=1)
        pandas.testing.assert_frame_equal(df, self.sum_df)

    def test_summary_df_from_list(self):
        data_list = [self.data[i, :] for i in range(self.nrows)]
        df = nestcheck.pandas_functions.summary_df_from_list(
            data_list, self.col_names, true_values=np.zeros(self.ncols),
            include_true_values=True, include_rmse=True)
        pandas.testing.assert_frame_equal(df, self.sum_df)

    def test_summary_df_from_multi(self):
        multi = self.df
        multi['method'] = 'method 1'
        multi.set_index('method', drop=True, append=True, inplace=True)
        multi = multi.reorder_levels([1, 0])
        df = nestcheck.pandas_functions.summary_df_from_multi(
            multi, true_values=np.zeros(self.ncols),
            include_true_values=True, include_rmse=True)
        pandas.testing.assert_frame_equal(df.xs('method 1', level='method'),
                                          self.sum_df)

    def test_efficiency_gain_df(self):
        data_list = [self.data[i, :] for i in range(self.nrows)]
        method_names = ['old', 'new']
        adjust_nsamp = np.asarray([1, 2])
        method_values = [data_list] * len(method_names)
        df = nestcheck.pandas_functions.efficiency_gain_df(
            method_names, method_values, est_names=self.col_names,
            true_values=np.zeros(self.ncols),
            include_true_values=True, include_rmse=True,
            adjust_nsamp=adjust_nsamp)
        for i, method in enumerate(method_names[1:]):
            gains = np.asarray([adjust_nsamp[0] / adjust_nsamp[i + 1]] *
                               self.ncols)
            for gain_type in ['rmse efficiency gain', 'std efficiency gain']:
                numpy.testing.assert_array_equal(
                    df.loc[(gain_type, method, 'value'), :].values, gains)
        self.assertRaises(
            TypeError, nestcheck.pandas_functions.efficiency_gain_df,
            method_names, method_values, est_names=self.col_names,
            unexpected=1)
        # Use the efficiency gain df we just made to check
        # paper_format_efficiency_gain_df
        paper_df = nestcheck.pandas_functions.paper_format_efficiency_gain_df(df)
        cols = [col for col in self.col_names if col != 'samples']
        numpy.testing.assert_array_equal(
            paper_df[cols].values,
            df.loc[pd.IndexSlice[['std', 'std efficiency gain'], :, :], cols].values)


class TestAnalyseRun(unittest.TestCase):

    def test_combine_threads(self):
        """Check combining threads when birth contours are not present or are
        duplicated."""
        nsamples = 5
        ndim = 2
        # Get two threads
        threads = [get_dummy_ns_thread(nsamples, ndim, seed=False),
                   get_dummy_ns_thread(nsamples, ndim, seed=False)]
        # Sort in order of final logl
        threads = sorted(threads, key=lambda run: run['logl'][-1])
        t1 = threads[0]
        t2 = threads[1]
        # Get another thread starting on the last point of t2 (meaning it will
        # not overlap with t1)
        t_no_overlap = get_dummy_ns_thread(nsamples, ndim, seed=False,
                                           logl_start=t2['logl'][-1] + 1000)
        # combining with t1 should throw an assertion error as nlive drops to
        # zero in between the threads
        self.assertRaises(AssertionError, ar.combine_threads, [t1, t_no_overlap],
                          assert_birth_point=False)
        # Get another thread starting on the last point of t1 so it overlaps
        # with t2
        t3 = get_dummy_ns_thread(nsamples, ndim, seed=False,
                                 logl_start=t1['logl'][-1])
        # When birth point not in run:
        # Should raise assertion error only if assert_birth_point = True
        ar.combine_threads([t2, t3])
        self.assertRaises(AssertionError, ar.combine_threads, [t2, t3],
                          assert_birth_point=True)
        # When birth point in run once:
        # should work with assert_birth_point = True
        ar.combine_threads([t1, t2, t3], assert_birth_point=True)
        # When birth point in run twice:
        # Should raise assertion error only if assert_birth_point = True
        ar.combine_threads([t1, t1, t2, t3])
        self.assertRaises(AssertionError, ar.combine_threads, [t1, t1, t2, t3],
                          assert_birth_point=True)

    def test_bootstrap_resample_run(self):
        run = get_dummy_ns_run(2, 1, 2)
        run['settings'] = {'ninit': 1}
        # With only 2 threads and ninit=1, separating initial threads means
        # that the resampled run can only contain each thread once
        resamp = ar.bootstrap_resample_run(run, ninit_sep=True)
        self.assertTrue(np.array_equal(run['theta'], resamp['theta']))
        # With random_seed=1 and 2 threads each with a single points,
        # bootstrap_resample_run selects the second thread twice.
        resamp = ar.bootstrap_resample_run(run, random_seed=0)
        numpy.testing.assert_allclose(
            run['theta'][0, :], resamp['theta'][0, :])
        numpy.testing.assert_allclose(
            run['theta'][1, :], resamp['theta'][1, :])
        # Check error handeled if no ninit
        del run['settings']
        resamp = ar.bootstrap_resample_run(run, ninit_sep=True)

    def test_rel_posterior_mass(self):
        self.assertTrue(np.array_equal(
            ar.rel_posterior_mass(np.asarray([0, 1]), np.asarray([1, 0])),
            np.asarray([1, 1])))

    def test_run_std_bootstrap(self):
        """Check bootstrap std is zero when the run only contains one
        thread."""
        run = get_dummy_ns_run(1, 10, 2)
        stds = ar.run_std_bootstrap(run, [e.param_mean], n_simulate=10)
        self.assertAlmostEqual(stds[0], 0, places=12)
        self.assertRaises(TypeError, ar.run_std_bootstrap, run,
                          [e.param_mean], n_simulate=10, unexpected=1)

    def test_run_ci_bootstrap(self):
        """Check bootstrap ci equals estimator expected value when the
        run only contains one thread."""
        run = get_dummy_ns_run(1, 10, 2)
        ci = ar.run_ci_bootstrap(run, [e.param_mean], n_simulate=10,
                                 cred_int=0.5)
        self.assertAlmostEqual(ci[0], e.param_mean(run), places=12)

    def test_run_std_simulate(self):
        """Check simulate std is zero when the run only contains one
        point."""
        run = get_dummy_ns_run(1, 1, 2)
        stds = ar.run_std_simulate(run, [e.param_mean], n_simulate=10)
        self.assertAlmostEqual(stds[0], 0, places=12)

    def test_get_logw(self):
        """Check IndexError raising"""
        self.assertRaises(IndexError, ar.get_logw,
                          {'nlive_array': np.asarray(1.),
                           'logl': np.asarray([])})


class TestEstimators(unittest.TestCase):

    def setUp(self):
        self.nsamples = 10
        self.ns_run = get_dummy_ns_run(1, self.nsamples, 2)
        self.logw = ar.get_logw(self.ns_run)
        self.w_rel = np.exp(self.logw - self.logw.max())
        self.w_rel /= np.sum(self.w_rel)

    def test_count_samples(self):
        """Check count_samples estimator."""
        self.assertEqual(e.count_samples(self.ns_run), self.nsamples)

    def test_run_estimators(self):
        """Check ar.run_estimators wrapper is working."""
        out = ar.run_estimators(self.ns_run, [e.count_samples])
        self.assertEqual(out.shape, (1,))  # out should be np array
        self.assertEqual(out[0], self.nsamples)

    def test_logx(self):
        """Check logx estimator."""
        self.assertAlmostEqual(e.logz(self.ns_run),
                               scipy.special.logsumexp(self.logw), places=12)

    def test_evidence(self):
        """Check evidence estimator."""
        self.assertAlmostEqual(e.evidence(self.ns_run),
                               np.exp(scipy.special.logsumexp(self.logw)),
                               places=12)

    def test_param_mean(self):
        """Check param_mean estimator."""
        self.assertAlmostEqual(e.param_mean(self.ns_run),
                               np.sum(self.w_rel * self.ns_run['theta'][:, 0]),
                               places=12)

    def test_param_squared_mean(self):
        """ Check param_squared_mean estimator."""
        self.assertAlmostEqual(
            e.param_squared_mean(self.ns_run),
            np.sum(self.w_rel * (self.ns_run['theta'][:, 0] ** 2)),
            places=12)

    def test_r_mean(self):
        """Check r_mean estimator."""
        r = np.sqrt(self.ns_run['theta'][:, 0] ** 2 +
                    self.ns_run['theta'][:, 1] ** 2)
        self.assertAlmostEqual(e.r_mean(self.ns_run),
                               np.sum(self.w_rel * r), places=12)

    def test_param_cred(self):
        """Check param_cred estimator."""
        # Check results agree with np.median when samples are equally weighted
        self.assertAlmostEqual(
            e.param_cred(self.ns_run, logw=np.zeros(self.nsamples)),
            np.median(self.ns_run['theta'][:, 0]), places=12)
        # Check another probability while using weighted samples
        prob = 0.84
        self.assertAlmostEqual(
            e.param_cred(self.ns_run, probability=prob),
            e.weighted_quantile(prob, self.ns_run['theta'][:, 0], self.w_rel),
            places=12)

    def test_r_cred(self):
        """Check r_cred estimator."""
        r = np.sqrt(self.ns_run['theta'][:, 0] ** 2 +
                    self.ns_run['theta'][:, 1] ** 2)
        # Check results agree with np.median when samples are equally weighted
        self.assertAlmostEqual(
            e.r_cred(self.ns_run, logw=np.zeros(self.nsamples)), np.median(r),
            places=12)
        # Check another probability while using weighted samples
        prob = 0.84
        self.assertAlmostEqual(
            e.r_cred(self.ns_run, probability=prob),
            e.weighted_quantile(prob, r, self.w_rel),
            places=12)


class TestEstimatorLatexNames(unittest.TestCase):

    def test_outputs_unique_strings(self):
        """
        Check get_latex_names produces a unique string for each of a list of
        commonly used estimators.
        """
        estimator_list = [e.count_samples,
                          e.logz,
                          e.evidence,
                          e.param_mean,
                          functools.partial(e.param_mean, param_ind=1),
                          e.param_squared_mean,
                          functools.partial(e.param_cred, probability=0.5),
                          functools.partial(e.param_cred, probability=0.84),
                          e.r_mean,
                          functools.partial(e.r_cred, probability=0.5),
                          functools.partial(e.r_cred, probability=0.84)]
        estimator_names = [e.get_latex_name(est) for est in estimator_list]
        for name in estimator_names:
            self.assertIsInstance(name, str)
        # Check names are unique
        self.assertEqual(len(estimator_names), len(set(estimator_names)))

    def test_latex_name_unexpected_kwargs(self):
        self.assertRaises(TypeError, e.get_latex_name, e.logz, unexpected=1)

    def test_latex_name_unknown_func(self):
        self.assertRaises(AssertionError, e.get_latex_name, np.mean)


class TestParallelUtils(unittest.TestCase):

    def setUp(self):
        """Define some variables."""
        self.x = list(range(5))
        self.func = parallel_apply_func
        self.func_args = (1,)
        self.func_kwargs = {'kwarg': 2}

    def test_parallel_apply_parallelised(self):
        """Check parallel_apply with parallel=True."""
        results_list = nestcheck.parallel_utils.parallel_apply(
            self.func, self.x, func_args=self.func_args,
            func_kwargs=self.func_kwargs, parallel=True)
        res_arr = np.vstack(results_list)
        self.assertTrue(np.all(res_arr[:, 1] == self.func_args[0]))
        self.assertTrue(np.all(res_arr[:, 2] == self.func_kwargs['kwarg']))
        # Need to sort results as may come back in any order
        self.assertTrue(np.array_equal(np.sort(res_arr[:, 0]),
                                       np.asarray(self.x)))

    def test_parallel_apply_not_parallelised(self):
        """Check parallel_apply with parallel=False."""
        results_list = nestcheck.parallel_utils.parallel_apply(
            self.func, self.x, func_args=self.func_args,
            func_kwargs=self.func_kwargs, parallel=False)
        res_arr = np.vstack(results_list)
        self.assertTrue(np.all(res_arr[:, 1] == self.func_args[0]))
        self.assertTrue(np.all(res_arr[:, 2] == self.func_kwargs['kwarg']))
        # Don't need to sort res_arr[:, 0] as will be in order when
        # parallel=False
        self.assertTrue(np.array_equal(res_arr[:, 0], np.asarray(self.x)))

    def test_parallel_apply_unexpected_kwargs(self):
        """Unexpected kwarg should throw exception."""
        self.assertRaises(TypeError, nestcheck.parallel_utils.parallel_apply,
                          self.func, self.x, func_args=self.func_args,
                          unexpected=1)

    def test_parallel_map_not_parallelised(self):
        """Check parallel_map with parallel=False."""
        func_pre_args = self.func_args
        results_list = nestcheck.parallel_utils.parallel_map(
            self.func, self.x, func_pre_args=func_pre_args,
            func_kwargs=self.func_kwargs, parallel=False)
        res_arr = np.vstack(results_list)
        self.assertTrue(np.all(res_arr[:, 0] == func_pre_args[0]))
        self.assertTrue(np.all(res_arr[:, 2] == self.func_kwargs['kwarg']))
        # Don't need to sort as will be in order for map
        self.assertTrue(np.array_equal(res_arr[:, 1], np.asarray(self.x)))

    def test_parallel_map_parallelised(self):
        """Check parallel_map with parallel=True."""
        func_pre_args = self.func_args
        results_list = nestcheck.parallel_utils.parallel_map(
            self.func, self.x, func_pre_args=func_pre_args,
            func_kwargs=self.func_kwargs, parallel=True)
        res_arr = np.vstack(results_list)
        self.assertTrue(np.all(res_arr[:, 0] == func_pre_args[0]))
        self.assertTrue(np.all(res_arr[:, 2] == self.func_kwargs['kwarg']))
        # Don't need to sort as will be in order for map
        self.assertTrue(np.array_equal(res_arr[:, 1], np.asarray(self.x)))

    def test_parallel_map_unexpected_kwargs(self):
        """Unexpected kwarg should throw exception."""
        self.assertRaises(TypeError, nestcheck.parallel_utils.parallel_map,
                          self.func, self.x, unexpected=1)


class TestDiagnostics(unittest.TestCase):

    def test_run_list_error_summary(self):
        run_list = []
        for _ in range(10):
            run_list.append(get_dummy_ns_run(1, 10, 2))
        df = nestcheck.diagnostics.run_list_error_summary(
            run_list, [e.param_mean], ['param_mean'], 10, thread_pvalue=True,
            bs_stat_dist=True, cache_root='temp', save=False, load=True)
        self.assertTrue(np.all(~np.isnan(df.values)))
        # Uncomment below line to update values if they are deliberately
        # changed:
        df.to_pickle('tests/run_list_error_summary.pkl')
        # Check the values of every row for the theta1 estimator
        test_values = pd.read_pickle('tests/run_list_error_summary.pkl')
        numpy.testing.assert_allclose(df.values, test_values.values,
                                      rtol=1e-13, atol=1e-13)

    def test_run_list_error_values_unexpected_kwarg(self):
        self.assertRaises(
            TypeError, nestcheck.diagnostics.run_list_error_values,
            [], [e.param_mean], ['param_mean'], 10, thread_pvalue=True,
            bs_stat_dist=True, save=True, load=True, unexpected=1)


class TestPlots(unittest.TestCase):

    def setUp(self):
        """Get some dummy data to plot."""
        self.ns_run = get_dummy_ns_run(10, 100, 2)
        nestcheck.data_processing.check_ns_run(self.ns_run,
                                               logl_warn_only=True)

    def test_plot_run_nlive(self):
        fig = nestcheck.plots.plot_run_nlive(
            ['standard'], {'standard': [self.ns_run] * 2})
        self.assertIsInstance(fig, matplotlib.figure.Figure)
        self.assertRaises(
            TypeError, nestcheck.plots.plot_run_nlive,
            ['standard'], {'standard': [self.ns_run] * 2}, unexpected=0)

    @unittest.skipIf(importlib.util.find_spec('fgivenx') is None,
                     'needs fgivenx to run')
    def test_param_logx_diagram(self):
        fig = nestcheck.plots.param_logx_diagram(
            self.ns_run, n_simulate=3, npoints=100)
        self.assertIsInstance(fig, matplotlib.figure.Figure)
        self.assertRaises(
            TypeError, nestcheck.plots.param_logx_diagram,
            self.ns_run, unexpected=0)

    @unittest.skipIf(importlib.util.find_spec('fgivenx') is None,
                     'needs fgivenx to run')
    def test_bs_param_dists(self):
        fig = nestcheck.plots.bs_param_dists(
            self.ns_run, n_simulate=3, nx=10)
        self.assertIsInstance(fig, matplotlib.figure.Figure)
        self.assertRaises(
            TypeError, nestcheck.plots.bs_param_dists,
            self.ns_run, unexpected=0)

    def test_kde_plot_df(self):
        bs_df = pd.DataFrame(index=['run_1', 'run_2'])
        bs_df['estimator_1'] = [np.random.random(10)] * 2
        bs_df['estimator_2'] = [np.random.random(10)] * 2
        fig = nestcheck.plots.kde_plot_df(bs_df)
        self.assertIsInstance(fig, matplotlib.figure.Figure)
        self.assertRaises(
            TypeError, nestcheck.plots.kde_plot_df,
            unexpected=0)


# helper functions

def parallel_apply_func(x, arg, kwarg=-1):
    """A test function for checking parallel_apply."""
    return np.asarray([x, arg, kwarg])


def get_dummy_ns_run(nlive, nsamples, ndim, seed=False):
    """Generate template ns runs for quick testing without loading test
    data."""
    threads = []
    if seed is not False:
        np.random.seed(seed)
    for _ in range(nlive):
        threads.append(get_dummy_ns_thread(nsamples, ndim, seed=False))
    return ar.combine_ns_runs(threads)


def get_dummy_ns_thread(nsamples, ndim, seed=False, logl_start=-np.inf):
    """Generate a single ns thread for quick testing without loading test
    data."""
    thread = {'logl': np.sort(np.random.random(nsamples)),
              'nlive_array': np.full(nsamples, 1.),
              'theta': np.random.random((nsamples, ndim)),
              'thread_labels': np.zeros(nsamples).astype(int)}
    if logl_start != -np.inf:
        thread['logl'] += logl_start
    thread['thread_min_max'] = np.asarray([[logl_start, thread['logl'][-1]]])
    return thread


def get_dummy_dead_points(ndims=2, nsamples=10):
    """
    Make a dead points array of the type produced by PolyChord. Also returns
    the same nested sampling run as a dictionary in the standard nestcheck
    format for checking.
    """
    threads = [get_dummy_ns_thread(nsamples, ndims, seed=False,
                                   logl_start=-np.inf)]
    threads.append(get_dummy_ns_thread(nsamples, ndims, seed=False,
                                       logl_start=threads[0]['logl'][0]))
    threads[-1]['thread_labels'] += 1
    # to make sure thread labels derived from the dead points match the
    # order in threads, we need to make sure the first point after the
    # contour where 2 points are born (threads[0]['logl'][0]) is in
    # threads[0] not threads[-1]. Hence add to threads[-1]['logl']
    threads[-1]['logl'] += 1
    threads[-1]['thread_min_max'][0, 1] += 1
    print(threads)
    dead_arrs = []
    for th in threads:
        dead = np.zeros((nsamples, ndims + 2))
        dead[:, :ndims] = th['theta']
        dead[:, ndims] = th['logl']
        dead[1:, ndims + 1] = th['logl'][:-1]
        if th['thread_min_max'][0, 0] == -np.inf:
            dead[0, ndims + 1] = -1e30
        else:
            dead[0, ndims + 1] = th['thread_min_max'][0, 0]
        dead_arrs.append(dead)
    dead = np.vstack(dead_arrs)
    dead = dead[np.argsort(dead[:, ndims]), :]
    run = ar.combine_threads(threads)
    return dead, run

if __name__ == '__main__':
    unittest.main()
