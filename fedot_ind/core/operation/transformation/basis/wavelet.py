from typing import Optional, Tuple

import pywt
from fedot.core.operations.operation_parameters import OperationParameters
from pymonad.either import Either
from pymonad.list import ListMonad

from fedot_ind.core.architecture.settings.computational import backend_methods as np
from fedot_ind.core.operation.transformation.basis.abstract_basis import BasisDecompositionImplementation
from fedot_ind.core.repository.constanst_repository import CONTINUOUS_WAVELETS, DISCRETE_WAVELETS, WAVELET_SCALES


class WaveletBasisImplementation(BasisDecompositionImplementation):
    """Wavelet basis
        Example:
            ts1 = np.random.rand(200)
            ts2 = np.random.rand(200)
            ts = [ts1, ts2]
            bss = WaveletBasisImplementation({'n_components': 2, 'wavelet': 'mexh'})
            basis_multi = bss._transform(ts)
            basis_1d = bss._transform(ts1)
    """

    def __init__(self, params: Optional[OperationParameters] = None):
        super().__init__(params)
        self.n_components = params.get('n_components')
        self.wavelet = params.get('wavelet')
        self.basis = None
        self.discrete_wavelets = DISCRETE_WAVELETS
        self.continuous_wavelets = CONTINUOUS_WAVELETS
        self.scales = WAVELET_SCALES

    def __repr__(self):
        return 'WaveletBasisImplementation'

    def _decompose_signal(self, input_data) -> Tuple[np.array, np.array]:
        if self.wavelet in self.discrete_wavelets:
            high_freq, low_freq = pywt.dwt(input_data, self.wavelet, 'smooth')
        else:
            high_freq, low_freq = pywt.cwt(data=input_data,
                                           scales=self.scales,
                                           wavelet=self.wavelet)
            low_freq = high_freq[-1, :]
            high_freq = np.delete(high_freq, (-1), axis=0)
            low_freq = low_freq[np.newaxis, :]
        return high_freq, low_freq

    def _decomposing_level(self) -> int:
        """The level of decomposition of the time series.

        Returns:
            The level of decomposition of the time series.
        """
        return pywt.dwt_max_level(len(self.time_series), self.wavelet)

    def _transform_one_sample(self, series: np.array):
        return self._get_basis(series)

    def _get_1d_basis(self, data) -> np.array:

        def decompose(signal): return ListMonad(self._decompose_signal(signal))

        def threshold(Monoid): return ListMonad([Monoid[0][
            :self.n_components],
            Monoid[1]])

        basis = Either.insert(data).then(decompose).then(threshold).value[0]
        basis = np.concatenate(basis)
        return basis

    def _get_multidim_basis(self, data):
        def decompose(multidim_signal): return ListMonad(
            list(map(self._decompose_signal, multidim_signal)))

        def select_level(Monoid): return [Monoid[0][
            :self.n_components, :],
            Monoid[1]]

        def threshold(decomposed_signal): return list(
            map(select_level, decomposed_signal))

        basis = Either.insert(data).then(decompose).then(threshold).value
        return np.concatenate([np.concatenate(x) for x in basis])
