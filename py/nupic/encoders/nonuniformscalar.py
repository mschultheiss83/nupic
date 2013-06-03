# ----------------------------------------------------------------------
#  Copyright (C) 2010 Numenta Inc. All rights reserved.
#
#  The information and source code contained herein is the
#  exclusive property of Numenta Inc. No part of this software
#  may be used, reproduced, stored or distributed in any form,
#  without explicit written authorization from Numenta Inc.
#   Author: Rahul Agarwal
# ----------------------------------------------------------------------

from scalar import *

class NonUniformScalarEncoder(ScalarEncoder):
  """
  This is an implementation of the scalar encoder that encodes
  the value into unequal ranges, such that each encoding occurs with
  approximately equal frequency.

  This means that value ranges that occur more frequently will have higher
  resolution than those that occur less frequently
  """

  ############################################################################
  def __init__(self, w, n, data = None, bins = None,
                      weights=None, name=None, verbosity=0):



    self._numBins = n - w + 1
    self.weights = weights
    super(NonUniformScalarEncoder, self).__init__(w=w, n=n, minval= 0, maxval=self._numBins-1,
                                                                          clipInput=True, name=name,
                                                                          verbosity=verbosity)
    hasData = data is None
    hasBins = bins is None
    if hasData == hasBins:
      raise ValueError("Exactly one argument must be supplied: data or bins")

    if data is not None:
      self.data = numpy.array(data)
      self.bins =  self.ComputeBins(self._numBins, self.data, self.weights, self.verbosity)

    if bins is not None:
      #if self._numBins != len(bins):
      #  raise ValueError(
      #    '''Incorrect number of bins for given resolution
      #    Num bins supplied:%d
      #    Num bins expected (according to n and w):%d''' %(len(bins), self._numBins))
      self.bins = numpy.array(bins)
      self._numBins = self.bins.shape[0]




  ############################################################################
  @classmethod
  def ComputeBins(cls, nBins, data, weights=None, verbosity = 0):
    data = numpy.array(data)
    bins = numpy.zeros((nBins, 2))
    #If no weights were specified, default to uniformly wieghted
    if weights is None:
      weights = numpy.ones(data.shape, dtype = defaultDtype)

    sortedIndices = numpy.argsort(data)
    sortedValues = data[sortedIndices]
    sortedWeights = weights[sortedIndices]
    cumWeights = numpy.cumsum(sortedWeights)
    avgBinWeight = cumWeights[-1] / nBins

    #Prepend 0s to the values and weights because we
    #are actually dealing with intervals, not values
    sortedValues = numpy.append(sortedValues[0], sortedValues)
    cumWeights = numpy.append(0, cumWeights)

    #-------------------------------------------------------------------------
    # Iterate through each bin and find the appropriate start
    # and end value for each one. We use the numpy.interp
    # function to deal with non-integer indices

    startValue = sortedValues[0]
    cumBinWeight = 0
    binIndex = 0

    if verbosity > 0:
      print "Average Bin Weight: %.3f"% avgBinWeight

    while True:
      # Use the inverse cumulative probability mass function
      # to compute the bin endpoint
      bins[binIndex, 0] = startValue
      cumBinWeight += avgBinWeight
      endValue = numpy.interp(cumBinWeight, xp=cumWeights, fp=sortedValues)
      bins[binIndex,1] = endValue

      if verbosity > 1:
          print "Start Value:%.2f EndValue:%.2f" %(startValue, endValue)

      if abs(cumWeights[-1] - cumBinWeight) < 1e-10:
        break

      startValue = endValue
      binIndex += 1

    # --------------------------------------------
    # Cleanup: if there are any identical bins, only leave one copy
    matches = (bins[0:-1, :] == bins[1:, :])
    if numpy.any(matches):
      # Assume the last bin is unique
      matches = numpy.vstack([matches, [False, False]])
      #matchingBins = numpy.all(matches, axis=1)
      matchingBins = matches[:,0]
      bins=bins[numpy.logical_not(matchingBins), :]

    #All done, print out if necessary
    if verbosity > 0:
      print "Bins:\n", bins
    return bins



  ############################################################################
  def getBucketIndices(self, input):
    """[ScalarEncoder class method override]"""

    if input != SENTINEL_VALUE_FOR_MISSING_DATA:
      bin = self._findBin(input)
    else:
      bin = SENTINEL_VALUE_FOR_MISSING_DATA

    return super(NonUniformScalarEncoder, self).getBucketIndices(bin)


  ############################################################################
  def encodeIntoArray(self, input, output):
    """[ScalarEncoder class method override]"""

    if input != SENTINEL_VALUE_FOR_MISSING_DATA:
      bin = self._findBin(input)
    else:
      bin = SENTINEL_VALUE_FOR_MISSING_DATA

    super(NonUniformScalarEncoder, self).encodeIntoArray(bin, output)


  ############################################################################
  def _findBin(self, value):
    assert self.bins is not None
    lower = value >= self.bins[:,0]
    upper = value < self.bins[:,1]

    # The last range is both left and right inclusive
    upper[-1] = (value <= self.bins[-1, -1])

    bins = numpy.where(numpy.logical_and(lower,upper))[0]

    if len(bins) == 0:
      if value < self.bins[0,0]:
        return -1
      elif value >= self.bins[-1,-1]:
        return self._numBins
      else:

        raise ValueError("Improper value for encoder: %f\nBins:%r" % (value, self.bins))
    else:
      assert len(bins)==1
      return bins[0]

  ############################################################################
  def decode(self, encoded, parentFieldName=""):
    """ Overidden from scalar.py"""

    (rangeDict, fieldNames) = super(NonUniformScalarEncoder, self).decode(encoded, parentFieldName)
    range = self._getRangeForEncoding(encoded, rangeDict, fieldNames)
    desc = self._generateRangeDescription([range])

    for fieldName, (bins, desc) in rangeDict.iteritems():
      rangeDict[fieldName] = ([range], desc)

    return (rangeDict, fieldNames)

  ############################################################################
  def _getRangeForEncoding(self, encoded, rangeDict, fieldNames):

    assert  len(rangeDict)==1

    (bins, description) = rangeDict.values()[0]
    assert len(bins)==1

    bin = bins[0]
    # if the decoding leads to a range of bin, just take the mean for now
    if bin[0] == bin[1]:
      binIndex = bin[0]
    else:
      binIndex = numpy.round(numpy.mean(bins))

    assert binIndex >= 0 and binIndex < self.bins.shape[0]
    curRange = self.bins[binIndex,:]
    ranges = list(curRange)

    return ranges

  ############################################################################
  def _getTopDownMapping(self):
    """ Return the interal _topDownMappingM matrix used for handling the
    bucketInfo() and topDownCompute() methods. This is a matrix, one row per
    category (bucket) where each row contains the encoded output for that
    category.
    """

    if self._topDownMappingM is None:
      self._topDownMappingM = SM32(self._numBins, self.n)

      outputSpace = numpy.zeros(self.n, dtype = GetNTAReal())

      for i in xrange(self._numBins):
        outputSpace[:] = 0.0
        outputSpace[i:i+self.w] = 1.0
        self._topDownMappingM.setRowFromDense(i, outputSpace)

    return self._topDownMappingM

  ############################################################################
  def getBucketValues(self):
    """ See the function description in base.py """

    if self._bucketValues is None:
      topDownMappingM = self._getTopDownMapping()
      numBuckets = topDownMappingM.nRows()
      self._bucketValues = []
      for bucketIdx in range(numBuckets):
        self._bucketValues.append(self.getBucketInfo([bucketIdx])[0].value)

    return self._bucketValues

  ############################################################################
  def getBucketInfo(self, buckets):
    """ See the function description in base.py """

    topDownMappingM = self._getTopDownMapping()

    binIndex = buckets[0]
    value = numpy.mean(self.bins[binIndex, :])

    return [EncoderResult(value=value, scalar=value,
                         encoding=self._topDownMappingM.getRow(binIndex))]

  ############################################################################
  def topDownCompute(self, encoded):
    """ See the function description in base.py """

    topDownMappingM = self._getTopDownMapping()

    binIndex = topDownMappingM.rightVecProd(encoded).argmax()
    value = numpy.mean(self.bins[binIndex, :])

    return [EncoderResult(value=value, scalar=value,
                         encoding=self._topDownMappingM.getRow(binIndex))]

############################################################################
  def dump(self):
    print "NonUniformScalarEncoder:"
    print " ranges: %r"% self.bins
    print "  w:   %d" % self.w
    print "  n:   %d" % self.n
    print "  resolution: %f" % self.resolution
    print "  radius:     %f" % self.radius
    print "  nInternal: %d" % self.nInternal
    print "  rangeInternal: %f" % self.rangeInternal
    print "  padding: %d" % self.padding

############################################################################
def testNonUniformScalarEncoder():
  import numpy.random
  print "Testing NonUniformScalarEncoder..."

  def testEncoding(value, expected, encoder):
    observed = None
    expected = numpy.array(expected, dtype=defaultDtype)
    try:
      observed = encoder.encode(value)
      assert(observed == expected).all()
    except :
      #print "Encoding Error: encoding value %f \
      #\nexpected %s. got %s "% (value, str(expected), str(observed))
      print "Encoder Bins:\n%s"% encoder.bins
      raise Exception("Encoding Error: encoding value %f \
                                expected %s\n got %s "%
                                (value, str(expected), str(observed)))

  # TODO: test parent class methods
  #
  # -----------------------------------------
  # Start with simple uniform case:
  print "\t*Testing uniform distribution*"

  data = numpy.linspace( 1, 10, 10, endpoint = True)
  enc = NonUniformScalarEncoder(w=7,n=16, data=data, verbosity=3)
  expectedEncoding = numpy.zeros(16)
  expectedEncoding[:7] = 1
  for i in range(1,10):
    testEncoding(i, expectedEncoding, enc)
    expectedEncoding = numpy.roll(expectedEncoding, 1)

  testEncoding(10, [0,0,0,0,0,0,0,0,1,1,1,1,1,1,1,0], enc)
  del enc

  ## -----------------------------------------
  # Make sure the encoder works with a larger set of
  # bins and skewed distributions
  print "\t*Testing skewed distribution*"
  data = numpy.linspace(0, 10, 100)
  data = numpy.append(data, numpy.linspace(10,20,200))
  # Shuffle the data so that the order doesn't matter
  numpy.random.shuffle(data)
  enc = NonUniformScalarEncoder(w = 7, n=9, data=data)

  testEncoding(5, [1,1,1,1,1,1,1,0,0], enc)
  testEncoding(9, [1,1,1,1,1,1,1,0,0], enc)
  testEncoding(10, [0,1,1,1,1,1,1,1,0], enc)
  testEncoding(14.9, [0,1,1,1,1,1,1,1,0], enc)
  testEncoding(15, [0,0,1,1,1,1,1,1,1], enc)
  testEncoding(19, [0,0,1,1,1,1,1,1,1], enc)

  del enc

  ## -----------------------------------------
  ## Make sure the encoder works with non-uniform wieghts
  ## bins and very skewed distributions
  print "\t*Testing weighted distribution*"
  data = numpy.linspace(0, 10, 100)
  weights= 4 * numpy.ones_like(data)
  data = numpy.append(data, numpy.linspace(10,20,200))
  weights = numpy.append(weights, numpy.ones(200))
  enc = NonUniformScalarEncoder(w = 7, n=9, data=data, weights=weights)

  testEncoding(3, [1,1,1,1,1,1,1,0,0], enc)
  testEncoding(5, [0,1,1,1,1,1,1,1,0], enc)
  testEncoding(9, [0,1,1,1,1,1,1,1,0], enc)
  testEncoding(10, [0,0,1,1,1,1,1,1,1], enc)
  testEncoding(15, [0,0,1,1,1,1,1,1,1], enc)

  del enc
  #
  ## -----------------------------------------
  ## Stress test: make sure that ranges still
  ## make sense if there are a lot of bins
  print "\t*Stress Test*"
  data = numpy.concatenate([numpy.repeat(10, 30),
                                              numpy.repeat(5, 20),
                                              numpy.repeat(20, 35)])
  enc = NonUniformScalarEncoder(w=7, n=100, data=data, verbosity=2)
  result = numpy.zeros(100, dtype=defaultDtype)
  result[0:7] = 1
  testEncoding(5, result, enc)



  ##  Now test a very discontinuous distribution
  #TODO: Not really sure what should happen here
  #data = 10 * numpy.ones(500)
  #data[250:] *= 2
  #enc = NonUniformScalarEncoder(w =3, n=4, data=data, verbosity = 2)
  #
  #assert enc.resolution == 1.0
  #assert enc._numBins == 2
  ##assert(enc.bins == numpy.array([[0,10.0], [10.0, 20.0]])).all()
  #
  #testEncoding(-1, [1,1,1,0], enc)
  #testEncoding(5, [1,1,1,0], enc)
  #testEncoding(10, [0,1,1,1], enc)
  #testEncoding(15, [0,1,1,1], enc)
  #testEncoding(25, [0,1,1,1], enc)
  #del enc
  #
  ## -----------------------------------------
  ## Now a case similar to the first, but with the proportions slightly uneven
  ## TODO: What should actually happen here ?
  #print "\t*Testing uneven distribution*"
  #data = 10 * numpy.ones(500)
  #data[248:] *= 2
  #enc = NonUniformScalarEncoder(w =3, n=4, data=data, verbosity = 0)
  #testEncoding(9, [1,1,1,0], enc)
  #testEncoding(10, [1,1,1,0], enc)
  #testEncoding(20, [0,1,1,1], enc)
  #del enc


  ## -----------------------------------------
  ## Test top-down decoding
  print "\t*Testing top-down decoding*"
  data = numpy.random.random_sample(400)
  enc = NonUniformScalarEncoder(w=7, n=9, data=data, verbosity=3)
  print enc.dump()
  output = numpy.array([1,1,1,1,1,1,1,0,0], dtype=defaultDtype)
  for i in xrange(enc.n - enc.w + 1):
    topdown = enc.topDownCompute(output)
    bin = enc.bins[i,:]
    assert topdown[0].value >= bin[0] and topdown[0].value < bin[1]
    output = numpy.roll(output, 1)

  print "\t*Test TD decoding with explicit bins*"
  bins = [[   0. ,    199.7  ],
    [ 199.7,   203.1  ],
    [ 203.1,    207.655],
    [ 207.655,  212.18 ],
    [ 212.18,   214.118],
    [ 214.118,  216.956],
    [ 216.956,  219.133]]

  enc = NonUniformScalarEncoder(w=7, n=13, bins=bins)

  # -----------------------------------------
  # Test TD compute on
  tdOutput = numpy.array([ 0.0, 0.0, 0.0, 0.0, 0.40000001, 1.0,
                        1.0, 1.0, 1.0, 1.0, 1.0, 0.60000002,
                        0.60000002])
  enc.topDownCompute(tdOutput)
  topdown = enc.topDownCompute(tdOutput)
  testEncoding(topdown[0].value, [0,0,0,0,0,1,1,1,1,1,1,1,0], enc)
  # -----------------------------------------
  print "\t*Test TD decoding with non-contiguous ranges*"

  tdOutput = numpy.array([ 1.0, 1.0, 1.0, 0.0, 0.0, 0.0,
                        1.0, 1.0, 1.0, 1.0, 1.0, 0.60000002,
                        0.60000002])

  topdown = enc.topDownCompute(tdOutput)
  testEncoding(topdown[0].value, [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1,1], enc)

  print "passed"

############################################################################
if __name__ == '__main__':
  testNonUniformScalarEncoder()