import numpy as np
import pandas as pd
import networkx as nx
import random
import kmapper as km
import netrd

from kmapper import KeplerMapper, Cover
from sklearn.cluster import DBSCAN
from netrd.distance import NetSimile
from tmap.tda.utils import optimize_dbscan_eps

class CoverTuning():
    """
    A class for tuning Cover parameters in TDA Mapper using NetSimile as graph distance metric.
    
    Attributes:
    - data (pd.DataFrame): The input dataset
    - projector (class): The dimensionality reduction technique to use for the TDA Mapper
    - res_range (list): The range of resolution values to test
    - gain_range (list): The range of gain values to test
    - n_bootstrap (int): The number of bootstrap samples to generate
    - seed_value (int): The seed value for reproducibility
    """
    def __init__(self, data, projector, res_range, gain_range, n_bootstrap, seed_value):
        """Initializes the CoverTuning class with the specified parameters."""
        super().__init__()
        self.data = data
        self.projector = projector
        self.mapper = KeplerMapper(verbose=0)
        self.res_range = res_range
        self.gain_range = gain_range
        self.n_bootstrap = n_bootstrap
        self.seed_value = seed_value

    def create_tda_graph(self, x, perc_overlap, n_cubes):
        """
        Creates a TDA Mapper graph based on the input dataset and specified Cover parameters.

        Parameters:
        - x (np.ndarray): The input dataset
        - perc_overlap (float): The percentage overlap for the Cover
        - n_cubes (int): The number of cubes for the Cover

        Returns:
        - nx.Graph: A NetworkX graph representing the TDA Mapper output
        """
        lens = self.mapper.fit_transform(x, self.projector(n_components=2, random_state=self.seed_value))
        graph = self.mapper.map(
            lens, X=x,
            cover=Cover(perc_overlap=perc_overlap, n_cubes=n_cubes),
            clusterer=DBSCAN(eps=optimize_dbscan_eps(x, threshold=95), min_samples=2)
        )

        return km.adapter.to_nx(graph)
    
    def get_bootstrap_sample(self, sample_ratio=0.7):
        """
        Generates a collection of bootstrap samples from the input dataset.

        Parameters:
        - sample_ratio (float, optional): The ratio of samples to be drawn from the dataset 
        for each bootstrap iteration. Defaults to 0.7

        Returns:
        - List: A list containing numpy arrays representing the bootstrap samples
        """
        data_idx = self.data.index.tolist()
        idx_bootstrap = {}
        bootstrap_data = []

        random.seed(self.seed_value)

        for i in range(0, self.n_bootstrap):
            y = random.sample(data_idx, round(len(data_idx)*sample_ratio))
            idx_bootstrap[i] = y
            idx_bootstrap_df = pd.DataFrame(idx_bootstrap)

            current_idx = idx_bootstrap_df.iloc[:,i].to_list()
            all_data = self.data.iloc[current_idx,:]
            bootstrap_data.append(all_data)

        X_arrays = [array.to_numpy() for array in bootstrap_data]
        return X_arrays
    
    def graph_distance_metric(self, graph_list):
        """
        Computes the average distance between graphs based on NetSimile.

        Parameters:
        - graph_list (list): A list of NetworkX graphs to compute distances between

        Returns:
        - float: The average distance between graphs based on NetSimile
        """
        distance = {}
        netsimile = NetSimile()

        n_graphs = len(graph_list)

        def avg_distance(distances):
            dist_values = list(distances.values())
            return sum(dist_values) / len(dist_values)
        
        for i in range(0, n_graphs):
            for j in range(i+1, n_graphs):

                # ij distance
                dist_key_ij = f'd{i+1}{j+1}'
                dist_ij_netsimile = netsimile.dist(graph_list[i], graph_list[j])

                # ji distance
                dist_key_ji = f'd{j+1}{i+1}'
                dist_ji_netsimile = netsimile.dist(graph_list[j], graph_list[i])

                if dist_ij_netsimile == dist_ji_netsimile:
                    distance[dist_key_ij] = dist_ij_netsimile
                else:
                    distance[dist_key_ij] = dist_ij_netsimile
                    distance[dist_key_ji] = dist_ji_netsimile

                return avg_distance(distance)
            
    def grid_search(self):
        """
        Conducts a grid search over the specified Cover parameter ranges and computes the average graph distance
        between the resulting TDA Mapper graphs using NetSimile.

        Returns:
        - np.ndarray: A matrix containing the average graph distances for each combination of Cover parameters
        """
        matrix = np.zeros((len(self.res_range), len(self.gain_range)))
        bootstrap_samples = self.get_bootstrap_sample()

        for i in range(0, len(self.res_range)):
            res_current = self.res_range[i]
            for j in range(0, len(self.gain_range)):
                print(f'ITERATION RES n.{i+1} out of {len(self.res_range)} TOT')
                print(f'ITERATION GAIN n.{j+1} out of {len(self.gain_range)} TOT')

                gain_current = self.gain_range[j]

                # Graph creation
                graph_list = []
                for k in range(0, len(bootstrap_samples)):
                    graph = self.create_tda_graph(bootstrap_samples[k], res_current, gain_current)
                    graph_list.append(graph)

                # Graph distance (NetSimile)
                dist = self.graph_distance_metric(graph_list)

                # Save results
                matrix[i,j] = dist

        return matrix
    
class GraphProperties(CoverTuning):
    def __init__(self, data, projector, res, gain, seed):
        super().__init__(data, projector, None, None, None, seed)
        self.data = data
        self.projector = projector
        self.res = res
        self.gain = gain
        self.seed = seed
    def graph_properties_stats(self):
        """
        Calculates statistical properties of a TDA graph based on specified Cover parameters.

        Parameters:
        - res (float): The resolution parameter determining the size of bins in the Cover
        - gain (int): The gain parameter determining the overlap between bins in the Cover

        Returns:
        - pd.DataFrame: A DataFrame containing the statistical properties of the TDA graph
        """
        graph = self.create_tda_graph(self.data, self.res, self.gain)

        # Graph properties
        graph_properties = netrd.distance.netsimile.feature_extraction(graph)
        graph_properties_signature = netrd.distance.netsimile.graph_signature(graph_properties)

        graph_properties_stats = graph_properties_signature.reshape((7,5))
        graph_properties_stats = graph_properties_stats.T

        row_names = ['mean', 'median', 'std', 'skewness', 'kurtosis']
        col_names = ['node degree', 'clustering coefficient', 'average degree of neighborhood', 
                     'average clustering coefficient of neighborhood', 'number of edges in the neighborhood', 
                     'number of outgoing edges from the neighborhood', 'number of neighbors of neighbors (not in neighborhood)']
        
        graph_properties_stats_df = pd.DataFrame(graph_properties_stats, columns=col_names, index=row_names)

        return graph_properties_stats_df







