"""Tests for RevBlock."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from tefla.core.special_fn import rev_block, recompute_grad
import tensorflow as tf


class RevBlockTest(tf.test.TestCase):
  CHANNELS = 8
  NUM_LAYERS = 4
  BATCH_SIZE = 16

  def _testRevBlock(self, x=None, f=None, g=None, f_side_input=None, g_side_input=None):
    tf.set_random_seed(1234)

    if f is None:

      def f(x):
        return tf.layers.dense(x, self.CHANNELS // 2, use_bias=True)

    if g is None:

      def g(x):
        return tf.layers.dense(x, self.CHANNELS // 2, use_bias=True)

    if f_side_input is None:
      f_side_input = []

    if g_side_input is None:
      g_side_input = []

    if x is None:
      x = tf.random_uniform([self.BATCH_SIZE, self.CHANNELS], dtype=tf.float32)
    x1, x2 = tf.split(x, 2, axis=-1)
    with tf.variable_scope("rev_test") as vs:
      y1_rev, y2_rev = rev_block(
          x1,
          x2,
          f,
          g,
          f_side_input=f_side_input,
          g_side_input=g_side_input,
          num_layers=self.NUM_LAYERS)
      y_rev = tf.concat([y1_rev, y2_rev], axis=1)
      fg_vars = vs.trainable_variables()

    num_vars = len(tf.global_variables())
    with tf.variable_scope(vs, reuse=True):
      y1, y2 = rev_block(
          x1,
          x2,
          f,
          g,
          f_side_input=f_side_input,
          g_side_input=g_side_input,
          num_layers=self.NUM_LAYERS,
          is_training=False)
      y = tf.concat([y1, y2], axis=1)
    # Ensure no new vars were created - full reuse
    assert len(tf.global_variables()) == num_vars

    loss_rev = tf.reduce_mean(y_rev + 10.)
    loss = tf.reduce_mean(y + 10.)

    wrt = [x] + f_side_input + g_side_input + fg_vars
    grads_rev = tf.gradients(loss_rev, wrt)
    grads = tf.gradients(loss, wrt)

    with self.test_session() as sess:
      sess.run(tf.global_variables_initializer())
      y_val, yd_val, gd_val, g_val = sess.run([y, y_rev, grads_rev, grads])
      self.assertAllClose(y_val, yd_val)
      for g1, g2 in zip(gd_val, g_val):
        self.assertAllClose(g1, g2)

  def testRevBlock(self):
    self._testRevBlock()

  def testSideInput(self):
    f_side_input = tf.random_uniform([self.BATCH_SIZE, self.CHANNELS // 2])

    def f(x, side_input):
      return tf.layers.dense(x, self.CHANNELS // 2, use_bias=True) + side_input[0]

    self._testRevBlock(f=f, f_side_input=[f_side_input])

  def testMultipleFns(self):

    def f1(x):
      return tf.layers.dense(x, self.CHANNELS // 2)

    def f2(x):
      return tf.layers.dense(x, self.CHANNELS // 2, activation=tf.nn.relu)

    self._testRevBlock(f=[f1, f2, f1, f2])

  def testConvAndBatchNorm(self):

    x = tf.random_uniform([self.BATCH_SIZE, 10, self.CHANNELS], dtype=tf.float32)

    def f(x):
      x = tf.layers.conv1d(x, self.CHANNELS // 2, 3, padding="same")
      x = tf.layers.batch_normalization(x, training=False)
      x = tf.layers.conv1d(x, self.CHANNELS // 2, 3, padding="same")
      x = tf.layers.batch_normalization(x, training=False)
      return x

    self._testRevBlock(x=x, f=f)


class RecomputeTest(tf.test.TestCase):

  def testRecompute(self):

    @recompute_grad
    def fn_recompute(x, y):
      return x + y, x**y

    def fn(x, y):
      return x + y, x**y

    x = tf.ones((3, 3))
    y = tf.ones((3, 3))
    out1 = tf.reduce_sum(fn_recompute(x, y))
    out2 = tf.reduce_sum(fn(x, y))

    grad1 = tf.gradients(out1, [x, y])
    grad2 = tf.gradients(out2, [x, y])

    with self.test_session() as sess:
      outs = sess.run([out1, out2, grad1, grad2])
      self.assertAllClose(outs[0], outs[1])
      for g1, g2 in zip(outs[2], outs[3]):
        self.assertAllClose(g1, g2)


if __name__ == "__main__":
  tf.test.main()
