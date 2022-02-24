import pandas as pd
import numpy as np

from sklearn import linear_model
from copy import deepcopy

from .base_models import BaseEstLearner
np.random.seed(2022)


class SLearner(BaseEstLearner):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        try:
            self.ml_model = self.ml_model_dic[kwargs['ml_model']]
        except Exception:
            self.ml_model = kwargs['ml_model']

    def prepare(self, data, outcome, treatment, adjustment, individual=None):
        """Prepare (fit the model) for estimating the quantities
            ATE: E[y|do(x_1)] - E[y|do(x_0)] = E_w[E[y|x=x_1,w] - E[y|x=x_0, w]
                                           := E_{adjustment}[
                                               Delta E[outcome|treatment,
                                                                adjustment]]
            CATE: E[y|do(x_1), z] - E[y|do(x_0), z] = E_w[E[y|x=x_1, w, z] -
                                                        E[y|x=x_0, w, z]]
            ITE: y_i(do(x_1)) - y_i(do(x_0))
            CITE: y_i(do(x_1))|z_i - y_i(do(x_0))|z_i

        Parameters
        ----------
        data : DataFrame
        outcome : string
            Name of the outcome.
        treatment : string
            Name of the treatment.
        adjustment : set or list
            The adjutment set for the causal effect,
            i.e., P(outcome|do(treatment)) =
                \sum_{adjustment} P(outcome|treatment, adjustment)P(adjustment)
        individual : DataFrame, default to None
            The individual data for computing its causal effect.

        Returns
        ----------
        np.array
        """
        x = list(adjustment)
        x.append(treatment)
        self.ml_model.fit(X=data[x], y=data[outcome])

        if individual:
            data = individual

        x1_data = pd.DataFrame.copy(data)
        x1_data[treatment] = 1
        x0_data = pd.DataFrame.copy(data)
        x0_data[treatment] = 0
        result = (
            self.ml_model.predict(x1_data[x]) -
            self.ml_model.predict(x0_data[x])
        )
        return result


class TLearner(BaseEstLearner):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        model = kwargs['ml_model']

        if type(model) is str:
            model = self.ml_model_dic[model]

        self.x1_model = model
        self.x0_model = deepcopy(model)

    def prepare(self, data, outcome, treatment, adjustment, individual=None):
        """Prepare (fit the model) for estimating the quantities
            ATE: E[y|do(x_1)] - E[y|do(x_0)] = E_w[E[y|x=x_1,w] - E[y|x=x_0, w]
                                           := E_{adjustment}[
                                               Delta E[outcome|treatment,
                                                                adjustment]]
            CATE: E[y|do(x_1), z] - E[y|do(x_0), z] = E_w[E[y|x=x_1, w, z] -
                                                        E[y|x=x_0, w, z]]
            ITE: y_i(do(x_1)) - y_i(do(x_0))
            CITE: y_i(do(x_1))|z_i - y_i(do(x_0))|z_i

        Parameters
        ----------
        data : DataFrame
        outcome : string
            Name of the outcome.
        treatment : string
            Name of the treatment.
        adjustment : set or list
            The adjutment set for the causal effect,
            i.e., P(outcome|do(treatment)) =
                \sum_{adjustment} P(outcome|treatment, adjustment)P(adjustment)
        individual : DataFrame, default to None
            The individual data for computing its causal effect.

        Returns
        ----------
        np.array
        """
        data_without_treatment = data.drop([treatment], axis=1)
        x1_data = data_without_treatment.loc[data[treatment] > 0]
        x0_data = data_without_treatment.loc[data[treatment] <= 0]
        self.x1_model.fit(x1_data[adjustment], x1_data[outcome])
        self.x0_model.fit(x0_data[adjustment], x0_data[outcome])

        if individual:
            data_ = individual[adjustment]
        else:
            data_ = data[adjustment]

        result = (
            self.x1_model.predict(data_) - self.x0_model.predict(data_)
        )
        return result


class XLearner(BaseEstLearner):
    """
    The XLearner is composed of 3 steps:
        1. Train two different models for the control group and treated group
            f_0(w), f_1(w)
        2. Generate two new datasets (h_0, w) using the control group and
            (h_1, w) using the treated group where
            h_0 = f_1(w) - y_0(w), h_1 = y_1(w) - f_0(w). Then train two models
            k_0(w) and k_1(w) in these datasets.
        3. Get the final model using the above two models:
            g(w) = k_0(w)a(w) + k_1(w)(1 - a(w)).
    Finally,  we estimate the ATE as follows:
        ATE = E_w(g(w)).
    See Kunzel, et al., (https://arxiv.org/abs/1706.03461) for reference.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        model = kwargs['ml_model']

        if type(model) is str:
            model = self.ml_model_dic[model]

        self.f1 = model
        self.f0 = deepcopy(model)
        self.k1 = deepcopy(model)
        self.k0 = deepcopy(model)

    def prepare(self, data, outcome, treatment, adjustment, individual=None):
        """Prepare (fit the model) for estimating the quantities
            ATE: E[y|do(x_1)] - E[y|do(x_0)] = E_w[E[y|x=x_1,w] - E[y|x=x_0, w]
                                           := E_{adjustment}[
                                               Delta E[outcome|treatment,
                                                                adjustment]]
            CATE: E[y|do(x_1), z] - E[y|do(x_0), z] = E_w[E[y|x=x_1, w, z] -
                                                        E[y|x=x_0, w, z]]
            ITE: y_i(do(x_1)) - y_i(do(x_0))
            CITE: y_i(do(x_1))|z_i - y_i(do(x_0))|z_i

        Parameters
        ----------
        data : DataFrame
        outcome : string
            Name of the outcome.
        treatment : string
            Name of the treatment.
        adjustment : set or list
            The adjutment set for the causal effect,
            i.e., P(outcome|do(treatment)) =
                \sum_{adjustment} P(outcome|treatment, adjustment)P(adjustment)
        individual : DataFrame, default to None
            The individual data for computing its causal effect.
        """
        # step 1
        data_without_treatment = data.drop([treatment], axis=1)
        x1_data = data_without_treatment.loc[data[treatment] > 0]
        x0_data = data_without_treatment.loc[data[treatment] <= 0]
        self.f1.fit(x1_data[adjustment], x1_data[outcome])
        self.f0.fit(x0_data[adjustment], x0_data[outcome])

        # setp 2
        h1_data = x1_data.drop(outcome, axis=1)
        h0_data = x0_data.drop(outcome, axis=1)
        h1 = x1_data[outcome] - self.f0.predict(h1_data[adjustment])
        h0 = self.f1.predict(h0_data[adjustment]) - x0_data[outcome]
        self.k1.fit(h1_data[adjustment], h1)
        self.k0.fit(h0_data[adjustment], h0)

        # step 3
        if individual:
            data_ = individual[adjustment]
        else:
            data_ = data[adjustment]
        # TODO: more choices of rho
        rho = 0.5
        result = rho * self.k1.predict(data_) - \
            (1 - rho) * self.k0.predict(data_)
        return result


# class DragonNet(MetaLearner):
#     """
#     See Shi., et al., (https://arxiv.org/pdf/1906.02120.pdf) for reference.

#     Args:
#         MetaLearner ([type]): [description]
#     """

#     def __init__(self) -> None:
#         super().__init__()
