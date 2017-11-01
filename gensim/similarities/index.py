#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2013 Radim Rehurek <me@radimrehurek.com>
# Licensed under the GNU LGPL v2.1 - http://www.gnu.org/licenses/lgpl.html
import os

from smart_open import smart_open
try:
    import cPickle as _pickle
except ImportError:
    import pickle as _pickle

from gensim.models.doc2vec import Doc2Vec
from gensim.models.word2vec import Word2Vec
from gensim.models.keyedvectors import KeyedVectors
try:
    from annoy import AnnoyIndex
except ImportError:
    raise ImportError(
        "Annoy has not been installed, if you wish to use the annoy indexer, please run `pip install annoy`"
    )


class AnnoyIndexer(object):
    """This class allows to use `Annoy <https://github.com/spotify/annoy>`_ as indexer for ``most_similar`` method
    from :class:`~gensim.models.word2vec.Word2Vec`, :class:`~gensim.models.doc2vec.Doc2Vec`
    and :class:`~gensim.models.keyedvectors.KeyedVectors` classes.
    """

    def __init__(self, model=None, num_trees=None):
        """
        Parameters
        ----------
        model : :class:`~gensim.models.word2vec.Word2Vec`, :class:`~gensim.models.doc2vec.Doc2Vec` or :class:`~gensim.models.keyedvectors.KeyedVectors`, optional (default = None)
            Model, that will be used as source for index.
        num_trees : int, optional (default = None)
            Number of trees for Annoy indexer.

        Examples
        --------
        >>> from gensim.similarities.index import AnnoyIndexer
        >>> from gensim.models import Word2Vec
        >>>
        >>> sentences = [['cute', 'cat', 'say', 'meow'], ['cute', 'dog', 'say', 'woof']]
        >>> model = Word2Vec(sentences, min_count=1, seed=1)
        >>>
        >>> indexer = AnnoyIndexer(model, 2)
        >>> model.most_similar("cat", topn=2, indexer=indexer)
        [('cat', 1.0), ('dog', 0.32011348009109497)]

        """
        self.index = None
        self.labels = None
        self.model = model
        self.num_trees = num_trees

        if model and num_trees:
            if isinstance(self.model, Doc2Vec):
                self.build_from_doc2vec()
            elif isinstance(self.model, Word2Vec):
                self.build_from_word2vec()
            elif isinstance(self.model, KeyedVectors):
                self.build_from_keyedvectors()
            else:
                raise ValueError("Only a Word2Vec, Doc2Vec or KeyedVectors instance can be used")

    def save(self, fname, protocol=2):
        """Save AnnoyIndexer instance.

        Parameters
        ----------
        fname : str
            Path to output file, will produce 2 files: `fname` - parameters and `fname`.d - :class:`~annoy.AnnoyIndex`.
        protocol : int
            Protocol for pickle, optional (default = 2).

        Notes
        -----
        This method save **only** index (**model isn't preserved**).

        """
        fname_dict = fname + '.d'
        self.index.save(fname)
        d = {'f': self.model.vector_size, 'num_trees': self.num_trees, 'labels': self.labels}
        with smart_open(fname_dict, 'wb') as fout:
            _pickle.dump(d, fout, protocol=protocol)

    def load(self, fname):
        """Load AnnoyIndexer instance

        Parameters
        ----------
        fname : str
            Path to dump with AnnoyIndexer.

        Examples
        --------
        >>> from gensim.similarities.index import AnnoyIndexer
        >>> from gensim.models import Word2Vec
        >>> from tempfile import mkstemp
        >>>
        >>> sentences = [['cute', 'cat', 'say', 'meow'], ['cute', 'dog', 'say', 'woof']]
        >>> model = Word2Vec(sentences, min_count=1, seed=1, iter=10)
        >>>
        >>> indexer = AnnoyIndexer(model, 2)
        >>> _, temp_fn = mkstemp()
        >>> indexer.save(temp_fn)
        >>>
        >>> new_indexer = AnnoyIndexer()
        >>> new_indexer.load(temp_fn)
        >>> new_indexer.model = model

        """
        fname_dict = fname + '.d'
        if not (os.path.exists(fname) and os.path.exists(fname_dict)):
            raise IOError(
                "Can't find index files '%s' and '%s' - Unable to restore AnnoyIndexer state." % (fname, fname_dict)
            )
        else:
            with smart_open(fname_dict) as f:
                d = _pickle.loads(f.read())
            self.num_trees = d['num_trees']
            self.index = AnnoyIndex(d['f'])
            self.index.load(fname)
            self.labels = d['labels']

    def build_from_word2vec(self):
        """Build an Annoy index using word vectors from a Word2Vec model"""

        self.model.init_sims()
        return self._build_from_model(self.model.wv.syn0norm, self.model.wv.index2word, self.model.vector_size)

    def build_from_doc2vec(self):
        """Build an Annoy index using document vectors from a Doc2Vec model"""

        docvecs = self.model.docvecs
        docvecs.init_sims()
        labels = [docvecs.index_to_doctag(i) for i in range(0, docvecs.count)]
        return self._build_from_model(docvecs.doctag_syn0norm, labels, self.model.vector_size)

    def build_from_keyedvectors(self):
        """Build an Annoy index using word vectors from a KeyedVectors model"""

        self.model.init_sims()
        return self._build_from_model(self.model.syn0norm, self.model.index2word, self.model.vector_size)

    def _build_from_model(self, vectors, labels, num_features):
        index = AnnoyIndex(num_features)

        for vector_num, vector in enumerate(vectors):
            index.add_item(vector_num, vector)

        index.build(self.num_trees)
        self.index = index
        self.labels = labels

    def most_similar(self, vector, num_neighbors):
        """Find the approximate `num_neighbors` most similar items.

        Parameters
        ----------
        vector : numpy.array
            Vector for word/document.
        num_neighbors : int
            Number of most similar items

        Returns
        -------
        [(str, float), ...]
            List of most similar items in format [(`item`, `cosine_distance`), ... ]

        """

        ids, distances = self.index.get_nns_by_vector(
            vector, num_neighbors, include_distances=True)

        return [(self.labels[ids[i]], 1 - distances[i] / 2) for i in range(len(ids))]
