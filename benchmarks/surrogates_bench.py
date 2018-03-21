from darch import searchers as se, surrogates as su, core as co
import benchmarks.datasets as datasets
import numpy as np
import torch
import matplotlib.pyplot as plt
import seaborn as sns; sns.set()

# TODO: Change the below imports when using PyTorch
import darch.contrib.search_spaces.tensorflow.dnn as search_dnn
from darch.contrib.evaluators.tensorflow.classification import SimpleClassifierEvaluator
from darch.contrib.search_spaces.tensorflow.common import D
from darch.contrib.datasets.dataset import InMemoryDataset
from darch.contrib.datasets.loaders import load_mnist
from sklearn.model_selection import train_test_split


# Python >= 3.5

# Some requirements of surrogate models:
# 1. They should be fast to evaluate (justification)
# 2. They should be accurate (replacement)

class CLSTMSurrogateModel(torch.nn.Module):
    """ The actual CLSTM model
    """
    def __init__(self, character_list, hidden_size, embedding_size):
        super(CLSTMSurrogateModel, self).__init__()
        # One embedding feeds 4 LSTMs
        self.embeddings = torch.nn.Embedding(len(character_list), embedding_size)
        self.lstm_in = []
        self.h0 = []
        self.c0 = []
        for i in range(4):
            # One LSTM for each input feature
            self.lstm_in.append(torch.nn.LSTM(embedding_size, hidden_size, 1))
            # Learnable initial hidden states and cell states
            self.h0.append(torch.nn.Parameter(torch.randn(1, 1, hidden_size)))
            self.c0.append(torch.nn.Parameter(torch.randn(1, 1, hidden_size)))
        # LSTM to read the concatenated outputs of the input LSTMs
        self.lstm_out = torch.nn.LSTM(4 * hidden_size, hidden_size, 1)
        self.h_out = torch.nn.Parameter(torch.randn(1, 1, hidden_size))
        self.c_out = torch.nn.Parameter(torch.randn(1, 1, hidden_size))
        self.fc_out = torch.nn.Linear(hidden_size, 1)
    def forward(self, feats):
        out_0 = self.embeddings(feats[0]).unsqueeze(1)
        out_1 = self.embeddings(feats[1]).unsqueeze(1)
        out_2 = self.embeddings(feats[2]).unsqueeze(1)
        out_3 = self.embeddings(feats[3]).unsqueeze(1)
        _, (out_0, _) = self.lstm_in[0](out_0, (self.h0[0], self.c0[0]))
        _, (out_1, _) = self.lstm_in[1](out_1, (self.h0[1], self.c0[1]))
        _, (out_2, _) = self.lstm_in[2](out_2, (self.h0[2], self.c0[2]))
        _, (out_3, _) = self.lstm_in[3](out_3, (self.h0[3], self.c0[3]))
        out = torch.cat((out_0, out_1, out_2, out_3), dim=2)
        _, (out, _) = self.lstm_out(out, (self.h_out, self.c_out))
        out = self.fc_out(out)
        return out



class CLSTMSurrogate(su.SurrogateModel):
    """ The CLSTM Surrogate Function
    """
    # Character LSTM: One LSTM for each feature vector,
    # For a total of 3, then concat the outputs and learn
    character_list = [chr(i) for i in range(ord('A'), ord('Z'))] + [
        chr(i) for i in range(ord('a'), ord('z') + 1)] + [
        chr(i) for i in range(ord('0'), ord('9') + 1)] + [
        '.', ':', '-', '_', '<', '>', '/', '=', '*', ' ', '|']
    char_to_index = {ch : idx for (idx, ch) in enumerate(character_list)}
    # Each input LSTM has an embedding size and hidden state of 128
    embedding_size = 128
    hidden_size = 128

    def __init__(self):
        self.model = CLSTMSurrogateModel(self.character_list, self.embedding_size, self.hidden_size)
        self.optimizer = torch.optim.Adam(self.model.parameters())
        self.loss_fn = torch.nn.MSELoss()

    def preprocess(self, feats):
        # Feats is a 4-tuple of a list of strings. Need to convert this into a tensor
        # Convert strings to tensor by mapping the characters to indicies in the character_list
        # Final output is a list of 4 Long Tensors
        output = []
        for i, feat in enumerate(feats):
            vec_feat = []
            for obj in feat:
                for char in obj:
                    vec_feat.append(self.char_to_index[char])
            output.append(torch.autograd.Variable(torch.LongTensor(vec_feat)))
        return output

    def eval(self, feats):
        return self.model(self.preprocess(feats)).data[0, 0, 0]

    def update(self, val, feats):
        self.optimizer.zero_grad()  # Zero out the gradient buffer
        # TODO: refactor api to pass this in as an arg?
        out = self.model(self.preprocess(feats)) # Need to copmute network output
        # Wrap true value in a Float Tensor Variable
        loss = self.loss_fn(out, torch.autograd.Variable(torch.FloatTensor([[val]]).unsqueeze(0)))
        loss.backward()
        self.optimizer.step()


class SearchSpaceFactory:
    def __init__(self, num_classes):
        self.num_classes = num_classes
    
    def get_search_space(self):
        co.Scope.reset_default_scope()
        inputs, outputs = search_dnn.dnn_net(self.num_classes)
        return inputs, outputs, {'learning_rate_init' : D([1e-2, 1e-3, 1e-4, 1e-5])}

def savefig(filename):
    plt.savefig('{}.png'.format(filename), bbox_inches='tight')



def test_clstm_surrogate():
    ## TODO: Remove Tensorflow dependency so TF doesn't eat up all GPU memory
    ## TODO: Only use PyTorch in the benchmark?

    # ## Choose our dataset and split train/valid/test data
    # datasets.IRIS('.temp/data')
    # # For tensorflow usage, hardcoding in the data, once I change the contrib to PyTorch, can use the dataloaders
    # def iris_labels(label):
    #         if label == b'Iris-setosa':
    #             return 0
    #         elif label == b'Iris-versicolor':
    #             return 1
    #         elif label == b'Iris-virginica':
    #             return 2
    # data = np.loadtxt('.temp/data/iris.data', delimiter=',', usecols=[0,1,2,3])
    # labels = np.loadtxt('.temp/data/iris.data', delimiter=',', usecols=[4], converters={4: iris_labels})
    # Split data
    # X_train, X_test, y_train, y_test = train_test_split(data, labels, test_size=0.33)
    # X_valid, X_test, y_valid, y_test = train_test_split(X_test, y_test, test_size=0.50)
    # Steal MNIST Tensorflow example data:
    (X_train, y_train, X_valid, y_valid, X_test, y_test) = load_mnist('.temp/data/mnist')
    # Define datasets for contrib tensorflow evaluator
    train_dataset = InMemoryDataset(X_train, y_train, True)
    val_dataset = InMemoryDataset(X_valid, y_valid, False)
    test_dataset = InMemoryDataset(X_test, y_test, False)


    num_classes = 10 # Change this per dataset


    ## Declare the model evaluator
    evaluator = SimpleClassifierEvaluator(train_dataset, val_dataset, num_classes, 
        './temp', max_eval_time_in_minutes=1.0, log_output_to_terminal=True)
    
    ## Define our search space
    search_space_fn = SearchSpaceFactory(num_classes).get_search_space

    ## Define our surrogate models
    clstm_sur = CLSTMSurrogate()
    baseline_sur = su.HashingSurrogate(1024, 100000)
    
    ## Choose our searching algorithm
    searcher_clstm = se.SMBOSearcher(search_space_fn, clstm_sur, 32, 0.2)
    searcher_baseline = se.SMBOSearcher(search_space_fn, baseline_sur, 32, 0.2)

    ## Search the model space
    clstm_pred_accs = []
    baseline_pred_accs = []
    clstm_true_accs = []
    baseline_true_accs = []


    num_iters = 128

    for _ in range(num_iters):
        for model, searcher, pred_accs, true_accs, mode in zip([clstm_sur, baseline_sur], [searcher_clstm, searcher_baseline],
            [clstm_pred_accs, baseline_pred_accs], [clstm_true_accs, baseline_true_accs], ['CLSTM', 'Baseline']):
            print(mode)
            # Sample from our searcher
            (inputs, outputs, hs, _, searcher_eval_token) = searcher.sample()
            # Since Searcher doesn't return the score, we recompute it again, should be cheap since that's a goal
            feats = su.extract_features(inputs, outputs, hs)
            score = model.eval(feats)
            print('Predicted score: {}'.format(score))
            pred_accs.append(score)
            # Get the true score
            # val_acc = evaluator.eval(inputs, outputs, hs)['val_acc']
            val_acc = evaluator.eval(inputs, outputs, hs)
            true_accs.append(val_acc)
            searcher.update(val_acc, searcher_eval_token)
    
    # Plot the accuracies
    plt.plot(np.arange(num_iters), baseline_pred_accs)
    plt.plot(np.arange(num_iters), baseline_true_accs)
    plt.plot(np.arange(num_iters), clstm_pred_accs)
    plt.plot(np.arange(num_iters), clstm_true_accs)
    plt.legend(['Baseline Pred', 'Baseline True', 'CLSTM Pred', 'CLSTM True'], loc='lower right')
    plt.xlabel('Iteration')
    plt.ylabel('Accuracy')
    savefig('test_fig')
    print('CLSTM Predictions:\n{}\nCLSTM Actual:\n{}\nBaseline Predictions:\n{}\nBaseline Actual:\n{}\n'.format(
        clstm_pred_accs, clstm_true_accs, baseline_pred_accs, baseline_true_accs
    ))
    # TODO: log the accuracies
    


if __name__ == '__main__':
    test_clstm_surrogate()