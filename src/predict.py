import os
import tensorflow as tf
from model import MyModel
from data_generator import _parse_function_test
import numpy as np
import imghdr
from tqdm import tqdm
from multiprocessing import cpu_count


# Parameters
# ==================================================
tf.flags.DEFINE_string("data_dir", "data/Public",
                       """Path to the data directory""")
tf.flags.DEFINE_string("checkpoint_dir", 'models/0_inception_resnet_v2',
                       """Path to checkpoint folder""")

tf.flags.DEFINE_integer("batch_size", 16,
                        """Batch Size (default: 32)""")
tf.flags.DEFINE_integer("num_threads", 8,
                        """Number of threads for data processing (default: 2)""")

tf.flags.DEFINE_integer('image_size', 299, 'Train image size')

tf.flags.DEFINE_string("net",
                       'inception_resnet_v2',
                       "[resnet_v2_{50,101,152,200}, inception_{v4,resnet_v2}]")

tf.flags.DEFINE_boolean("allow_soft_placement", True,
                        """Allow device soft device placement""")

FLAGS = tf.flags.FLAGS


def is_valid(img_path):
  if os.path.getsize(img_path) == 0:  # zero-byte files
    return False
  if imghdr.what(img_path) not in ['jpeg', 'png', 'gif']:  # invalid image files
    return False
  return True


def list_files():
  img_paths = []
  fns = []
  corrupted_fns = []
  for fn in tqdm(tf.gfile.ListDirectory(FLAGS.data_dir), 'Data Loading'):
    img_path = os.path.join(FLAGS.data_dir, fn)
    if is_valid(img_path):
      img_paths.append(img_path)
      fns.append(str(fn).split('.')[0])
    else:
      corrupted_fns.append(str(fn).split('.')[0])
  return img_paths, fns, corrupted_fns


def init_data_generator(img_paths, fns):
  with tf.device('/cpu:0'):
    num_batches = int(np.ceil(len(img_paths) / FLAGS.batch_size))

    img_paths = tf.convert_to_tensor(img_paths, dtype=tf.string)
    fns = tf.convert_to_tensor(fns, dtype=tf.string)
    dataset = tf.data.Dataset.from_tensor_slices((img_paths, fns))
    dataset = dataset.map(_parse_function_test, num_parallel_calls=cpu_count())
    dataset = dataset.batch(FLAGS.batch_size)
    dataset = dataset.prefetch(FLAGS.batch_size)

    # create an reinitializable iterator given the dataset structure
    iterator = tf.data.Iterator.from_structure(dataset.output_types, dataset.output_shapes)
    init_data = iterator.make_initializer(dataset)
    get_next = iterator.get_next()

    return init_data, get_next, num_batches



def init_model(features):
  model = MyModel(FLAGS.net)
  logits, end_points = model(features, tf.constant(False, tf.bool))

  predictions = {
    'classes': tf.argmax(logits, axis=1),
    'top_3': tf.nn.top_k(logits, k=3)[1]
  }

  return predictions


def main(_):
  # Construct data generator
  img_paths, fns, corrupted_fns = list_files()
  init_data, get_next, num_batches = init_data_generator(img_paths, fns)

  # Build Graph
  x = tf.placeholder(tf.float32, shape=[None, FLAGS.image_size, FLAGS.image_size, 3])
  predictions = init_model(features=x)

  submit_file = open('submissions/{}_submission_{}.csv'.format(len(os.listdir('submissions/')), FLAGS.net), 'w')
  submit_file.write('id,predicted\n')

  # Create a session
  session_conf = tf.ConfigProto(allow_soft_placement=FLAGS.allow_soft_placement)
  with tf.Session(config=session_conf) as sess:
    checkpoint_dir = os.path.join(FLAGS.checkpoint_dir)
    saver = tf.train.Saver()
    saver.restore(sess, tf.train.latest_checkpoint(checkpoint_dir))
    print('Loaded model from %s' % checkpoint_dir)

    sess.run(init_data)
    loop = tqdm(range(num_batches), 'Inference')
    for _ in loop:
      # Get next batch of data
      img_batch, fn_batch = sess.run(get_next)
      _top3_preds = sess.run(predictions['top_3'], feed_dict={x: img_batch})

      for fn, preds in zip(fn_batch, _top3_preds):
        submit_file.write('{},{}\n'.format(fn.decode("utf-8"),
                                           ' '.join([str(p) for p in preds.tolist()])))

    for fn in corrupted_fns:
      submit_file.write('{},93 83 2\n'.format(fn))

    submit_file.close()
    print('Done')


if __name__ == '__main__':
  tf.app.run()
