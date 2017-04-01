from model import CRNN, CtcCriterion
from dataset import DatasetLmdb, SynthLmdb
import os
import tensorflow as tf
import numpy as np
import signal
import utility
import sys
import time

class Conf:
	def __init__(self):
		self.nClasses = 36
		self.trainBatchSize = 100
		self.evalBatchSize = 200
		self.testBatchSize = 10
		self.maxIteration = 2000000
		self.displayInterval = 100
		self.evalInterval = 1000
		self.testInterval = 2000
		self.saveInterval = 50000
		self.modelDir = os.path.abspath(os.path.join('..', 'model', 'ckpt'))
		self.dataSet = os.path.join('..', 'data', 'Synth')
		self.auxDataSet = os.path.join('..', 'data', 'aux_Synth')
		# self.dataSet = os.path.join('..', 'data', 'IIIT5K')
		self.maxLength = 24


if __name__ == '__main__':
	gConfig = Conf()
	sess = tf.InteractiveSession()

	ckpt = utility.checkPointLoader(gConfig.modelDir)
	imgs = tf.placeholder(tf.float32, [None, 32, 100])
	labels = tf.sparse_placeholder(tf.int32)
	batches = tf.placeholder(tf.int32, [None])
	isTraining = tf.placeholder(tf.bool)
	keepProb = tf.placeholder(tf.float32)
	pred_labels = tf.placeholder(tf.string, [None])
	true_labels = tf.placeholder(tf.string, [None])

	trainSeqLength = [gConfig.maxLength for i in range(gConfig.trainBatchSize)]
	testSeqLength = [gConfig.maxLength for i in range(gConfig.testBatchSize)]
	evalSeqLength = [gConfig.maxLength for i in range(gConfig.evalBatchSize)]

	crnn = CRNN(imgs, gConfig, isTraining, keepProb, sess)
	ctc = CtcCriterion(crnn.prob, labels, batches, pred_labels, true_labels)

	if ckpt is None:
		global_step = tf.Variable(0)
		optimizer = tf.train.AdadeltaOptimizer(0.001).minimize(ctc.cost, global_step=global_step)
		init = tf.global_variables_initializer()
		sess.run(init)
		step = 0
	else:
		global_step = tf.Variable(0)
		optimizer = tf.train.AdadeltaOptimizer(0.001).minimize(ctc.cost, global_step=global_step)
		crnn.loadModel(ckpt)
		step = sess.run([global_step])

	data = DatasetLmdb(gConfig.dataSet)
	# data = SynthLmdb(gConfig.dataSet, gConfig.auxDataSet)
	
	trainAccuracy = 0

	def signal_handler(signal, frame):
		print('You pressed Ctrl+C!')
		crnn.saveModel(gConfig.modelDir, step)
		print("%d steps trained model has saved" % step)
		sys.exit(0)
	signal.signal(signal.SIGINT, signal_handler)
	start_time = time.time()
	t = start_time
	while True:
		#train
		batchSet, labelSet = data.nextBatch(gConfig.trainBatchSize)
		cost, _, step = sess.run([ctc.cost, optimizer, global_step],feed_dict={
					crnn.inputImgs:batchSet, 
					crnn.isTraining:True,
					crnn.keepProb:0.5,
					ctc.target:labelSet, 
					ctc.nSamples:trainSeqLength
					})
		if step % gConfig.displayInterval == 0:
			time_elapse = time.time() - t
			t = time.time()
			total_time = time.time() - start_time
			print("step: %s, cost: %s, step time: %.2fs, total time: %.2fs" % (step, cost, time_elapse, total_time))
		#eval accuarcy
		if step != 0 and step % gConfig.evalInterval == 0:
			batchSet, labelSet = data.nextBatch(gConfig.evalBatchSize)
			# print(batchSet.shape, labelSet.shape)
			p = sess.run(ctc.decoded, feed_dict={
								crnn.inputImgs:batchSet, 
								crnn.isTraining:False,
								crnn.keepProb:1.0,
								ctc.target:labelSet, 
								ctc.nSamples:evalSeqLength
								})
			original = utility.convertSparseArrayToStrs(labelSet)
			predicted = utility.convertSparseArrayToStrs(p[0])
			# trainAccuracy = sess.run([ctc.accuracy], feed_dict={
			# 						ctc.pred_labels: predicted,
			# 						ctc.true_labels: original
			# 						})
			trainAccuracy = utility.eval_accuracy(predicted, original)
			print("step: %d, training accuracy %f" % (step, trainAccuracy))
		#small test
		if step != 0 and step % gConfig.testInterval == 0:
			batchSet, labelSet = data.nextBatch(gConfig.testBatchSize)
			p = sess.run(ctc.decoded, feed_dict={
								crnn.inputImgs:batchSet, 
								crnn.isTraining:False,
								crnn.keepProb:1.0,
								ctc.target:labelSet, 
								ctc.nSamples:testSeqLength
								})
			original = utility.convertSparseArrayToStrs(labelSet)
			predicted = utility.convertSparseArrayToStrs(p[0])
			for i in range(len(original)):
				print("original: %s, predicted: %s" % (original[i], predicted[i]))
		if step >= gConfig.maxIteration:
			print("%d training has completed" % gConfig.maxIteration)
			crnn.saveModel(gConfig.modelDir, step)
			sys.exit(0)
		if step != 0 and step % gConfig.saveInterval == 0:
			print("%d training has saved" % step)
			crnn.saveModel(gConfig.modelDir, step)