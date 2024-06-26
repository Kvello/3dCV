""" CS4277/CS5477 Lab 4: Plane Sweep Stereo
See accompanying Jupyter notebook (lab4.ipynb) for instructions.

Name: Markus Kvello
Email: e1163359@u.nus.edu
NUSNET ID: e1163359

"""
import json
import os
import math
import cv2
import numpy as np
from scipy.spatial.transform import Rotation
import scipy.ndimage
import matplotlib.pyplot as plt
np.set_printoptions(precision=6)  # Print less digits

"""Helper functions: You should not have to touch the following functions.
"""


class Image(object):
    """
    Image class. You might find the following member variables useful:
    - image: RGB image (HxWx3) of dtype np.float64
    - pose_mat: 3x4 Camera extrinsics that transforms points from world to
        camera frame
    """

    def __init__(self, qvec, tvec, name, root_folder=''):
        self.qvec = qvec
        self.tvec = tvec
        self.name = name  # image filename
        self._image = self.load_image(os.path.join(root_folder, name))

        # Extrinsic matrix: Transforms from world to camera frame
        self.pose_mat = self.make_extrinsic(qvec, tvec)

    def __repr__(self):
        return '{}: qvec={}\n tvec={}'.format(
            self.name, self.qvec, self.tvec
        )

    @property
    def image(self):
        return self._image.copy()

    @staticmethod
    def load_image(path):
        """Loads image and converts it to float64"""
        im = cv2.imread(path)
        im = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
        return im.astype(np.float64) / 255.0

    @staticmethod
    def make_extrinsic(qvec, tvec):
        """ Make 3x4 camera extrinsic matrix from colmap pose

        Args:
            qvec: Quaternion as per colmap format (q_cv) in the order
                  q_w, q_x, q_y, q_z
            tvec: translation as per colmap format (t_cv)

        Returns:

        """
        rotation = Rotation.from_quat(np.roll(qvec, -1))
        return np.concatenate([rotation.as_matrix(), tvec[:, None]], axis=1)


def write_json(outfile, images, intrinsic_matrix, img_hw):
    """Write metadata to json file.

    Args:
        outfile (str): File to write to
        images (list): List of Images
        intrinsic_matrix (np.ndarray): 3x3 intrinsic matrix
        img_hw (tuple): (image height, image width)
    """

    img_height, img_width = img_hw

    images_meta = []
    for im in images:
        images_meta.append({
            'name': im.name,
            'qvec': im.qvec.tolist(),
            'tvec': im.tvec.tolist(),
        })

    data = {
        'img_height': img_height,
        'img_width': img_width,
        'K': intrinsic_matrix.tolist(),
        'images': images_meta
    }
    with open(outfile, 'w') as fid:
        json.dump(data, fid, indent=2)


def load_data(root_folder):
    """Loads dataset.

    Args:
        root_folder (str): Path to data folder. Should contain metadata.json

    Returns:
        images, K, img_hw
    """
    print('Loading data from {}...'.format(root_folder))
    with open(os.path.join(root_folder, 'metadata.json')) as fid:
        metadata = json.load(fid)

    images = []
    for im in metadata['images']:
        images.append(Image(np.array(im['qvec']), np.array(im['tvec']),
                            im['name'], root_folder=root_folder))
    img_hw = (metadata['img_height'], metadata['img_width'])
    K = np.array(metadata['K'])

    print('Loaded data containing {} images.'.format(len(images)))
    return images, K, img_hw


def invert_extrinsic(cam_matrix):
    """Invert extrinsic matrix"""
    irot_mat = cam_matrix[:3, :3].transpose()
    trans_vec = cam_matrix[:3, 3, None]

    inverted = np.concatenate([irot_mat,  -irot_mat @ trans_vec], axis=1)
    return inverted


def concat_extrinsic_matrix(mat1, mat2):
    """Concatenate two 3x4 extrinsic matrices, i.e. result = mat1 @ mat2
      (ignoring matrix dimensions)
    """
    r1, t1 = mat1[:3, :3], mat1[:3, 3:]
    r2, t2 = mat2[:3, :3], mat2[:3, 3:]
    rot = r1 @ r2
    trans = r1@t2 + t1
    concatenated = np.concatenate([rot, trans], axis=1)
    return concatenated


def rgb2hex(rgb):
    """Converts color representation into hexadecimal representation for K3D

    Args:
        rgb (np.ndarray): (N, 3) array holding colors

    Returns:
        hex (np.ndarray): array (N, ) of size N, each element indicates the
          color, e.g. 0x0000FF = blue
    """
    rgb_uint = (rgb * 255).astype(np.uint8)
    hex = np.sum(rgb_uint * np.array([[256 ** 2, 256, 1]]),
                 axis=1).astype(np.uint32)
    return hex


"""Functions to be implemented
"""
# Part 1


def get_plane_sweep_homographies(K, relative_pose, inv_depths):
    """Compute plane sweep homographies, assuming fronto parallel planes w.r.t.
    reference camera

    Args:
        K (np.ndarray): Camera intrinsic matrix (3,3)
        relative_pose (np.ndarray): Relative pose between the two cameras
          of shape (3, 4)
        inv_depths (np.ndarray): Inverse depths to warp of size (D, )

    Returns:
        homographies (D, 3, 3)
    """

    homographies = []

    """ YOUR CODE STARTS HERE """
    R = relative_pose[:, :3]
    t = relative_pose[:, 3]
    t = t.reshape(3, 1)
    N = np.array([0, 0, -1])
    N = N.reshape(3, 1)
    for inv_depth in inv_depths:
        # Compute the homography for the given inverse depth
        homographies.append(K @ (R - t @ N.T * inv_depth) @ np.linalg.inv(K))
    """ YOUR CODE ENDS HERE """

    return np.array(homographies)

# Part 2


def compute_plane_sweep_volume(images, ref_pose, K, inv_depths, img_hw):
    """Compute plane sweep volume, by warping all images to the reference camera
    fronto-parallel planes, before computing the variance for each pixel and
    depth.

    Args:
        images (list[Image]): List of images which contains information about
          the camera extrinsics for each image
        ref_pose (np.ndarray): Reference camera pose
        K (np.ndarray): 3x3 intrinsic matrix (assumed same for all cameras)
        inv_depths (list): List of inverse depths to consider for plane sweep
        img_hw (tuple): tuple containing (H, W), which are the output height
          and width for the plane sweep volume.

    Returns:
        ps_volume (np.ndarray):
          Plane sweep volume of size (D, H, W), with dtype=np.float64, where
          D is len(inv_depths), and (H, W) are the image heights and width
          respectively. Each element should contain the variance of all pixel
          intensities that warp onto it.
        accum_count (np.ndarray):
          Accumulator count of same size as ps_volume, and dtype=np.int32.
          Keeps track of how many images are warped into a certain pixel,
          i.e. the number of pixels used to compute the variance.
    """

    D = len(inv_depths)
    H, W = img_hw
    ps_volume = np.zeros((D, H, W), dtype=np.float64)
    accum_count = np.zeros((D, H, W), dtype=np.int32)

    """ YOUR CODE STARTS HERE """
    ref_index = 0
    window_size = 3
    for i, image in enumerate(images):
        if (image.pose_mat == ref_pose).all():
            ref_index = i
            print("ref index: ", ref_index)
    ref_image = images[ref_index].image
    images = [image for i, image in enumerate(images) if i!=ref_index]
    homographies = np.zeros((len(images), D, 3, 3),dtype=np.float64)
    for i, image in enumerate(images):
        R = ref_pose[:, :3]@image.pose_mat[:, :3].T
        t = ref_pose[:, 3] - R@image.pose_mat[:, 3]
        t = t.reshape(3, 1)
        M = np.block([[R, t]])
        homographies[i] = get_plane_sweep_homographies(K, M, inv_depths)
    for k in range(D):
        transformed_images = np.zeros((len(images), H, W, 3), dtype=np.float64)
        transform_mask = np.zeros((len(images), H, W), dtype=bool)
        for l, image in enumerate(images):
            transform_mask[l] = cv2.warpPerspective(
                np.ones((H, W), dtype=np.uint8), homographies[l, k], (W, H)
            ).astype(bool)
            transformed_images[l] = cv2.warpPerspective(
                image.image, homographies[l, k], (W, H)
            )
            transformed_images[l][np.where(transform_mask[l]==0)] = ref_image[np.where(transform_mask[l]==0)]
            # plt.figure(figsize=(12,8))
            # plt.imshow(transformed_images[l])
            # plt.title("Transformed image number " + str(l) + " at depth " + str(inv_depths[k]))
            # plt.show()
        for x in range(window_size//2,H-window_size//2):
            for y in range(window_size//2,W-window_size//2):
                x_indces = np.arange(x-window_size//2, x+window_size//2+1)
                y_indces = np.arange(y-window_size//2, y+window_size//2+1)
                ch_r_diff = np.sum(np.abs(transformed_images[:, x_indces, y_indces, 0] - ref_image[x_indces,y_indces,0]))
                ch_g_diff = np.sum(np.abs(transformed_images[:, x_indces, y_indces, 1] - ref_image[x_indces,y_indces,1]))
                ch_b_diff = np.sum(np.abs(transformed_images[:, x_indces, y_indces, 2] - ref_image[x_indces,y_indces,2]))
                ps_volume[k, x, y] = (ch_r_diff + ch_g_diff + ch_b_diff)/3
                accum_count[k, x, y] = np.sum(transform_mask[:,x,y])
    """ YOUR CODE ENDS HERE """
    print(ps_volume.shape)

    return ps_volume, accum_count


def compute_depths(ps_volume, inv_depths):
    """Computes inverse depth map from plane sweep volume as the
    argmin over plane sweep volume variances.

    Args:
        ps_volume (np.ndarray): Plane sweep volume of size (D, H, W) from
          compute_plane_sweep_volume()
        inv_depths (np.ndarray): List of depths considered in the plane
          sweeping (D,)

    Returns:
        inv_depth_image (np.ndarray): inverse-depth estimate (H, W)
    """

    inv_depth_image = np.zeros(ps_volume.shape[1:], dtype=np.float64)

    """ YOUR CODE STARTS HERE """
    inv_depth_image = inv_depths[np.argmin(ps_volume, axis=0)]
    """ YOUR CODE ENDS HERE """

    return inv_depth_image


# Part 3
def post_process(ps_volume, inv_depths, accum_count):
    """Post processes the plane sweep volume and compute a mask to indicate
    which pixels have confident estimates of the depth

    Args:
        ps_volume: Plane sweep volume from compute_plane_sweep_volume()
          of size (D, H, W)
        inv_depths (List[float]): List of depths considered in the plane
          sweeping
        accum_count: Accumulator count from compute_plane_sweep_volume(), which
          can be used to indicate which pixels are not observed by many other
          images.

    Returns:
        inv_depth_image: Denoised Inverse depth image (similar to compute_depths)
        mask: np.ndarray of size (H, W) and dtype np.bool.
          Pixels with values TRUE indicate valid pixels.
    """

    mask = np.ones(ps_volume.shape[1:], dtype=np.bool)
    inv_depth_image = np.zeros(ps_volume.shape[1:], dtype=np.float64)
    # print(accum_count)
    """ YOUR CODE STARTS HERE """
    ps_volume =scipy.ndimage.median_filter(ps_volume, size=(9,9,9)) # Median filter to remove noise
    ps_volume[np.where(accum_count<5)] = np.inf # Ignore values with less than 5 observations
    inv_depth_image = inv_depths[np.argmin(ps_volume, axis=0)]
    inv_depth_image = scipy.ndimage.median_filter(inv_depth_image, size=(3,3)) # Second median filter to remove noise
    sobel_x = cv2.Sobel(inv_depth_image, cv2.CV_64F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(inv_depth_image, cv2.CV_64F, 0, 1, ksize=3)
    ret, mask = cv2.threshold(cv2.magnitude(sobel_x,sobel_y),inv_depth_image.mean()*0.1,1,cv2.THRESH_BINARY)
    mask = (1-mask).astype(bool)
    """ YOUR CODE ENDS HERE """

    return inv_depth_image, mask


# Part 4
def unproject_depth_map(image, inv_depth_image, K, mask=None):
    """Converts the depth map into points by unprojecting depth map into 3D

    Note: You will also need to implement the case where no mask is provided

    Args:
        image (np.ndarray): Image bitmap (H, W, 3)
        inv_depth_image (np.ndarray): Inverse depth image (H, W)
        K (np.ndarray): 3x3 Camera intrinsics
        mask (np.ndarray): Optional mask of size (H, W) and dtype=np.bool.

    Returns:
        xyz (np.ndarray): Nx3 coordinates of points, dtype=np.float64.
        rgb (np.ndarray): Nx3 RGB colors, where rgb[i, :] is the (Red,Green,Blue)
          colors for the points at position xyz[i, :]. Should be in the range
          [0, 1] and have dtype=np.float64.
    """

    xyz = np.zeros([0, 3], dtype=np.float64)
    rgb = np.zeros([0, 3], dtype=np.float64)  # values should be within (0, 1)
    H, W = image.shape[0:2]
    """ YOUR CODE STARTS HERE """
    K_inv = np.linalg.inv(K)
    grid_x, grid_y = np.meshgrid(np.arange(W), np.arange(H))
    points2d = np.array([[x,y,1] for x,y in zip(grid_x.flatten(), grid_y.flatten())])
    if mask is not None:
        points2d = points2d[np.where(mask.flatten())]
        inv_depth_image = inv_depth_image[mask]
        image = image[mask]
    scale = 1.0/inv_depth_image.flatten()
    points3d = (K_inv @ points2d.T).T * scale[:, np.newaxis]
    pointsrgb = image.reshape(-1, 3)
    """ YOUR CODE ENDS HERE """
    xyz = np.array(points3d)
    rgb = np.array(pointsrgb)
    return xyz, rgb

def main():
    ref_id = 4  # use image 4 as the reference view
    data_folder = 'data/tsukuba'
    images, K, (img_height, img_width) = load_data(data_folder)
    ref_pose = images[ref_id].pose_mat
    print('Reference camera pose:\n', ref_pose)

    # Visualizes the source images
    plt.figure(figsize=(12, 14))
    num_rows = math.ceil(len(images) / 3)
    plt.tight_layout()
    for i in range(len(images)):
        plt.subplot(num_rows, 3, i+1)
        plt.imshow(images[i].image)
        if i == ref_id:
            plt.title('Image {} (ref))'.format(i))
        else:
            plt.title('Image {}'.format(i))

    # Sweep D=256 planes from 0.8 to 6.0 meters away
    num_depths = 10
    inv_depths = np.linspace(1/0.8, 1/8.0, num=num_depths)
    ps_volume, accum_count = compute_plane_sweep_volume(images, ref_pose, K, inv_depths, 
                                                        (img_height, img_width))
    
    inv_depth_img = compute_depths(ps_volume, inv_depths)

    plt.figure(figsize=(12,8))
    plt.subplot(1,2,1)
    plt.imshow(images[ref_id].image)
    plt.title('Reference image')
    plt.subplot(1,2,2)
    plt.imshow(inv_depth_img)
    plt.title('Estimated depths')

    plt.figure(figsize=(12,14))
    for i in range(10):
        plt.subplot(4,3,i+1)
        dept_indx = i
        plt.imshow(ps_volume[dept_indx,:,:])
if __name__ == '__main__':
    main()