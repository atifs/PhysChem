import os
import json
import matplotlib.pyplot as plt


def tendency_pc(log: dict, path: str, higher_is_better=False, show_conf=False):
    epochs = [dic['epoch'] for dic in log]
    fig, ax1 = plt.subplots()
    if 'CVGAE' in path or 'HamEng' in path:
        pass
    else:
        train_p = [dic['train_p_metric'] for dic in log]
        valid_p = [dic['validate_p_metric'] for dic in log]
        test_p = [dic['test_p_metric'] for dic in log]
        ps = zip(valid_p, test_p)
        ps = sorted(ps, key=lambda x: x[0], reverse=higher_is_better)
        print('{}: {:.4f}'.format(path, ps[0][1]))

        ax1.plot(epochs, train_p, color='red', linestyle='--')
        ax1.plot(epochs, test_p, color='red')
        # ax1.set_ylim(min(train_p) - 0.2, max(train_p) + 0.2)

    if show_conf:
        # train_c = [dic['train_loss'] for dic in log]
        # test_c = [dic['test_loss'] for dic in log]
        train_c = [dic['train_c_metric'] for dic in log]
        valid_c = [dic['validate_c_metric'] for dic in log]
        test_c = [dic['test_c_metric'] for dic in log]
        ps = zip(valid_c, test_c)
        ps = sorted(ps, key=lambda x: x[0], reverse=False)
        print('{}: {:.4f} (conf)'.format(path, ps[0][1]))
        ax2 = ax1.twinx()
        ax2.plot(epochs, train_c, color='green', linestyle='--')
        ax2.plot(epochs, test_c, color='green')
        # ax2.set_ylim(min(train_c) - 0.1, max(train_c) + 0.1)

    plt.savefig(path)
    plt.close(fig)


tuples = [
    ('QM9', 'QM9', False, True),
    ('QM9', 'QM9-Xconf', False, True),
    ('QM9', 'QM9-rdkit', False, True),
    ('QM9', 'QM9-Oconf', False, True),
    ('QM9', 'QM9-real', False, False),
    ('QM9', 'CVGAE-QM9-rdkit', False, True),
    ('QM9', 'CVGAE-QM9-Xconf', False, True),
    ('QM9', 'HamEng-QM9', False, True),
    ('QM8', 'QM8@16880611', False, True),
    ('QM8', 'QM8-rdkit@16880611', False, True),
    ('QM8', 'QM8-Xconf@16880611', False, True),
    ('QM8', 'QM8-Oconf@16880611', False, True),
    ('QM8', 'QM8-real@16880611', False, False),
    ('QM8', 'CVGAE-QM8-rdkit@16880611', False, True),
    ('QM8', 'CVGAE-QM8-Xconf@16880611', False, True),
    ('QM8', 'HamEng@16880611', False, True),
    # ('QM7', 'HamEng@16880611', False, True),
    # ('QM7', 'QM7@16880611', False, True),
    # ('QM7', 'QM7-rdkit@16880611', False, True),
    # ('QM7', 'QM7-Xconf@16880611', False, True),
    # ('QM7', 'QM7-Oconf@16880611', False, True),
    ('QM7', 'QM7-real@16880611', False, False),
    # ('QM7', 'CVGAE-QM7-rdkit@16880611', False, False),
    # ('QM7', 'CVGAE-QM7-Xconf@16880611', False, False),

    ('Lipop', 'Lipop@16880611', False, False),
    ('Lipop', 'Lipop-RGT@16880611', False, True),
    ('Lipop', 'Lipop-Xconf@16880611', False, False),

    # ('TOX21', 'TOX21', True, True),
    # ('TOX21', 'TOX21-Xconf', True, True),

    ('ESOL', 'ESOL@16880611', False, False),
    ('ESOL', 'ESOL-RGT@16880611', False, True),
    ('ESOL', 'ESOL-Xconf@16880611', False, False),

    ('FreeSolv', 'FreeSolv@16880611', False, False),
    ('FreeSolv', 'FreeSolv-RGT@16880611', False, True),
    ('FreeSolv', 'FreeSolv-Xconf@16880611', False, False),
]

for d, f, h, t in tuples:
    if not os.path.exists(d):
        os.mkdir(d)
    json_path = f'{d}/{f}.json'
    graph_path = f'{d}/{f}.png'
    try:
        with open(json_path) as fp:
            log = json.load(fp)
    except FileNotFoundError:
        continue
    tendency_pc(log, graph_path, h, t)
