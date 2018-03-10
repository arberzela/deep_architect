
from darch.contrib.datasets.loaders import load_mnist
from darch.contrib.evaluators.tensorflow.classification import SimpleClassifierEvaluator
from darch.contrib.datasets.dataset import InMemoryDataset
import darch.contrib.search_spaces.tensorflow.dnn as css_dnn
import darch.core as co
import darch.searchers as se
import darch.search_logging as sl
import darch.visualization as vi

class SearchSpaceFactory:
    def __init__(self, num_classes):
        self.num_classes = num_classes
    
    def get_search_space(self):
        co.Scope.reset_default_scope()
        inputs, outputs = css_dnn.dnn_net(self.num_classes)
        return inputs, outputs, {}

def main():
    num_classes = 10
    num_samples = 16
    (Xtrain, ytrain, Xval, yval, Xtest, ytest) = load_mnist('data/mnist')
    train_dataset = InMemoryDataset(Xtrain, ytrain, True)
    val_dataset = InMemoryDataset(Xval, yval, False)
    test_dataset = InMemoryDataset(Xtest, ytest, False)
    evaluator = SimpleClassifierEvaluator(train_dataset, val_dataset, num_classes, 
        './temp', max_eval_time_in_minutes=1.0, log_output_to_terminal=True)
    search_space_factory = SearchSpaceFactory(num_classes)

    searcher = se.RandomSearcher(search_space_factory.get_search_space)
    search_logger = sl.SearchLogger('./logs', 'test')
    for _ in xrange(num_samples):
        evaluation_logger = search_logger.get_current_evaluation_logger()
        inputs, outputs, hs, hyperp_value_lst, searcher_eval_token = searcher.sample()
        evaluation_logger.log_config(hyperp_value_lst, searcher_eval_token)
        evaluation_logger.log_features(inputs, outputs, hs)
        results = evaluator.eval(inputs, outputs, hs)
        evaluation_logger.log_results(results)      
        vi.draw_graph(outputs.values(), True, True, print_to_screen=False,
            out_folderpath=evaluation_logger.get_user_data_folderpath())
        searcher.update(results['val_acc'], searcher_eval_token)

if __name__ == '__main__':
    main()