#emacs: -*- mode: python-mode; py-indent-offset: 4; indent-tabs-mode: nil -*-
#ex: set sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the PyMVPA package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Utility class to compute the transfer error of classifiers."""

__docformat__ = 'restructuredtext'

import numpy as N

from sets import Set
from StringIO import StringIO
from math import log10, ceil
from sets import Set

from mvpa.misc.errorfx import MeanMismatchErrorFx
from mvpa.misc.state import State

if __debug__:
    from mvpa.misc import debug

class ConfusionMatrix(object):
    """Simple class for confusion matrix computation / display.

    Implementation is aimed to be simple, thus it delays actual
    computation of confusion matrix untill all data is acquired (to
    figure out complete set of labels. If testing data doesn't have a
    complete set of labels, but you like to include all labels,
    provide them as a parameter to constructor"""

    def __init__(self, labels=[], targets=None, predictions=None):
        """Initialize ConfusionMatrix with optional list of `labels`

        :Parameters:
        """

        self.__labels = labels
        """List of known labels"""
        self.__computed = False
        """Flag either it was computed for a given set of data"""
        self.__sets = []
        """Datasets (target, prediction) to compute confusion matrix on"""
        self.__matrix = None
        """Resultant confusion matrix"""

        if not targets is None or not predictions is None:
            if not targets is None and not predictions is None:
                self.add(targets=targets, predictions=predictions)
            else:
                raise ValueError, \
                      "Please provide none or both targets and predictions"


    def add(self, targets, predictions):
        """Add new results to the set of known results"""
        if len(targets)!=len(predictions):
            raise ValueError, \
                  "Targets[%d] and predictions[%d]" % (len(targets),
                                                       len(predictions)) + \
                  " have different number of samples"
        self.__sets.append( (targets, predictions) )
        self.__computed = False


    def _compute(self):
        """Actually compute the confusion matrix based on all the sets"""
        if self.__computed:
            return

        if __debug__:
            if not self.__matrix is None:
                debug("LAZY", "Have to recompute ConfusionMatrix %s" % `self`)

        # figure out what labels we have
        labels = list(reduce(lambda x,y: x.union(Set(y[0]).union(Set(y[1]))),
                             self.__sets,
                             Set(self.__labels)))
        labels.sort()
        self.__labels = labels          # store the recomputed labels

        Nlabels, Nsets = len(labels), len(self.__sets)

        if __debug__:
            debug("CM", "Got labels %s" % labels)

        # Create a matrix for all votes
        mat_all = N.zeros( (Nsets, Nlabels, Nlabels) )

        # create total number of samples of each label counts
        # just for convinience I guess since it can always be
        # computed from mat_all
        counts_all = N.zeros( (Nsets, Nlabels) )

        iset = 0
        for targets, predictions in self.__sets:
            # convert predictions into numpy array
            pred = N.array(predictions)

            # create the contingency table template
            mat = N.zeros( (len(labels), len(labels)), dtype = 'uint' )

            for t, tl in enumerate( labels ):
                for p, pl in enumerate( labels ):
                    mat_all[iset, t, p] = N.sum( pred[targets==tl] == pl )

            iset += 1                   # go to next set


        # for now simply compute a sum of votes across different sets
        # we might do something more sophisticated later on, and this setup
        # should easily allow it
        self.__matrix = N.sum(mat_all, axis=0)

        self.__computed = True


    def __str__(self, header=True, percents=True, summary=True, print_empty=False):
        """'Pretty print' the matrix"""
        self._compute()

        # some shortcuts
        labels = self.__labels
        matrix = self.__matrix

        out = StringIO()
        # numbers of different entries
        Nlabels = len(labels)
        Nsamples = N.sum(matrix, axis=1)
        Ndigitsmax = int(ceil(log10(max(Nsamples))))
        Nlabelsmax = max( [len(str(x)) for x in labels] )

        L = max(Ndigitsmax, Nlabelsmax)     # length of a single label/value
        res = ""

        prefixlen = Nlabelsmax+2+Ndigitsmax+1
        pref = ' '*(prefixlen) # empty prefix
        if header:
            # print out the header
            out.write(pref)
            for label in labels:
                label = str(label)      # make it a string
                # center damn label
                Nspaces = int(ceil((L-len(label))/2.0))
                out.write(" %%%ds%%s%%%ds"
                          % (Nspaces, L-Nspaces-len(label))
                          % ('', label, ''))
            out.write("\n")

            # underscores
            out.write("%s%s\n" % (pref, (" %s" % ("-" * L)) * Nlabels))

        if matrix.shape != (Nlabels, Nlabels):
            raise ValueError, "Number of labels %d doesn't correspond the size" + \
                  " of a confusion matrix %s" % (Nlabels, matrix.shape)

        correct = 0
        for i in xrange(Nlabels):
            # print the label
            if Nsamples[i] == 0:
                continue
            out.write("%%%ds {%%%dd}" % (Nlabelsmax, Ndigitsmax) % (labels[i], Nsamples[i])),
            for j in xrange(Nlabels):
                out.write(" %%%dd" % L % matrix[i, j])
            if percents:
                out.write(' [%6.2f%%]' % (matrix[i, i] * 100.0 / Nsamples[i]))
            correct += matrix[i, i]
            out.write("\n")

        if summary:
            out.write("%%-%ds%%s\n"
                      % prefixlen
                      % ("", "-"*((L+1)*Nlabels)))

            out.write("%%-%ds[%%6.2f%%%%]\n"
                      % (prefixlen + (L+1)*Nlabels)
                      % ("Total Correct {%d out of %d}" % (correct, sum(Nsamples)),
                         100.0*correct/sum(Nsamples) ))


        result = out.getvalue()
        out.close()
        return result


    @property
    def labels(self):
        self._compute()
        return self.__labels


    @property
    def matrix(self):
        self._compute()
        return self.__matrix



class TransferError(State):
    """Compute the transfer error of a (trained) classifier on a dataset.

    The actual error value is computed using a customizable error function.
    Optionally the classifier can be training by passing an additional
    training dataset to the __call__() method.
    """
    def __init__(self, clf, errorfx=MeanMismatchErrorFx(), labels=None):
        """Cheap initialization.

        Parameters
        ----------
        - `clf`: Classifier instance.
                 Either trained or untrained.
        - `errorfx`: Functor that computes a scalar error value from the
                     vectors of desired and predicted values (e.g. subclass
                     of ErrorFx)
        - `labels`: if provided, should be a set of labels to add on top of
                    the ones present in testdata
        """
        State.__init__(self)
        self.__clf = clf
        self.__errorfx = errorfx
        self.__labels = labels
        self._registerState('confusion')
        """TODO Think that labels might be also symbolic thus can't directly
                be indicies of the array
        """

    def __call__(self, testdata, trainingdata=None):
        """Compute the transfer error for a certain test dataset.

        If `trainingdata` is not `None` the classifier is trained using the
        provided dataset before computing the transfer error. Otherwise the
        classifier is used in it's current state to make the predictions on
        the test dataset.

        Returns a scalar value of the transfer error.
        """
        if not trainingdata == None:
            self.__clf.train(trainingdata)

        predictions = self.__clf.predict(testdata.samples)

        # compute confusion matrix
        if self.isStateEnabled('confusion'):
            self['confusion'] = ConfusionMatrix(
                labels=self.__labels, targets=testdata.labels,
                predictions=predictions)

        # TODO

        # compute error from desired and predicted values
        error = self.__errorfx(predictions,
                               testdata.labels)

        return error
