import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from typing import List


def plt_predict_actual_bond_energy(predict: List[float], actual: List[float],
                                   title: str = 'plt_3d', d: str = 'visualize/alignment/graph'):
    fig = plt.figure(figsize=(8, 8))
    plt.scatter(predict, actual)
    sns.regplot(predict, actual)
    plt.title(title)
    plt.savefig('{}/{}.png'.format(d, title))
    plt.close()
