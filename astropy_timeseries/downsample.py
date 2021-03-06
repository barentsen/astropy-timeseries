import warnings

import numpy as np
from astropy import units as u
from astropy.utils.exceptions import AstropyUserWarning

from .sampled import TimeSeries
from .binned import BinnedTimeSeries

__all__ = ['simple_downsample']


def reduceat(array, indices, function):
    """
    Manual reduceat functionality for cases where Numpy functions don't have a reduceat
    """
    result = [function(array[indices[i]:indices[i+1]]) for i in range(len(indices) - 1)]
    result.append(function(array[indices[-1]:]))
    return np.array(result)


def simple_downsample(time_series, time_bin_size, func=None, time_bin_start=None, n_bins=None):
    """
    Downsample a time series by binning values into bins with a fixed size,
    using a single function

    Parameters
    ----------
    time_series : :class:`~astropy_timeseries.TimeSeries`
        The time series to downsample.
    time_bin_size : `~astropy.units.Quantity`
        The time interval for the binned time series
    func : callable, optional
        The function to use for combining points in the same bin. Defaults
        to np.nanmean.
    time_bin_start : `~astropy.time.Time`, optional
        The start time for the binned time series. Defaults to the first
        time in the sampled time series.
    n_bins : int, optional
        The number of bins to use. Defaults to the number needed to fit all
        the original points.

    Returns
    -------
    binned_time_series : :class:`~astropy_timeseries.BinnedTimeSeries`
        The downsampled time series.
    """

    if not isinstance(time_series, TimeSeries):
        raise TypeError("time_series should be a TimeSeries")

    bin_size_sec = time_bin_size.to_value(u.s)

    # Use the table sorted by time
    sorted = time_series.iloc[:]

    # Determine start time if needed
    if time_bin_start is None:
        time_bin_start = sorted.time[0]

    # Find the relative time since the start time, in seconds
    relative_time_sec = (sorted.time - time_bin_start).sec

    # Determine the number of bins if needed
    if n_bins is None:
        n_bins = int(np.ceil(relative_time_sec[-1] / bin_size_sec))

    if func is None:
        func = np.nanmedian

    # Determine the bins
    relative_bins_sec = np.cumsum(np.hstack([0, np.repeat(bin_size_sec, n_bins)]))
    bins = time_bin_start + relative_bins_sec * u.s

    # Find the subset of the table that is inside the bins
    keep = ((relative_time_sec >= relative_bins_sec[0]) &
            (relative_time_sec < relative_bins_sec[-1]))
    subset = sorted[keep]

    # Figure out which bin each row falls in - the -1 is because items
    # falling in the first bins will have index 1 but we want that to be 0
    indices = np.searchsorted(relative_bins_sec, relative_time_sec[keep]) - 1

    # Create new binned time series
    binned = BinnedTimeSeries(time_bin_start=bins[:-1], time_bin_end=bins[-1])

    # Determine rows where values are defined
    groups = np.hstack([0, np.nonzero(np.diff(indices))[0] + 1])

    # Find unique indices to determine which rows in the final time series
    # will not be empty.
    unique_indices = np.unique(indices)

    # Add back columns

    for colname in subset.colnames:

        if colname == 'time':
            continue

        values = subset[colname]

        # FIXME: figure out how to avoid the following, if possible
        if not isinstance(values, (np.ndarray, u.Quantity)):
            warnings.warn("Skipping column {0} since it has a mix-in type", AstropyUserWarning)
            continue

        data = np.ma.zeros(n_bins, dtype=values.dtype)
        data.mask = 1

        if isinstance(values, u.Quantity):
            data[unique_indices] = u.Quantity(reduceat(values.value, groups, func),
                                              values.unit, copy=False)
        else:
            data[unique_indices] = reduceat(values, groups, func)

        data.mask[unique_indices] = 0
        binned[colname] = data

    return binned
