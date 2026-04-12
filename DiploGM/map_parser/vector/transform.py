import re
from xml.etree.ElementTree import Element
import numpy as np

class TransGL3:
    """Class to handle coordinate transformations using a 3x3 matrix.
    This parses transformation strings found in SVG elements, and turns them into a matrix."""
    def __init__(self, transform_string: str | Element | None=None):
        if transform_string is None:
            transform_string = ""
        if not isinstance(transform_string, str):
            transform_string = transform_string.get("transform", "")

        pre = None
        post = None
        self.matrix = np.array([
            [1, 0, 0],
            [0, 1, 0],
            [0 , 0 , 1]
        ])
        transform_string = transform_string.strip()

        if "matrix" in transform_string:
            match = re.search(r"matrix\((.*?),(.*?),(.*?),(.*?),(.*?),(.*?)\)", transform_string)
            if not match:
                raise ValueError(f"Malformed matrix transformation: {transform_string}")
            m = np.array([
                [float(match.group(1)), float(match.group(2)), 0],
                [float(match.group(3)), float(match.group(4)), 0],
                [float(match.group(5)), float(match.group(6)), 1]
            ])
            self.matrix = self.matrix @ m

        if "translate" in transform_string:
            match = re.search(r"translate\((.*?)\)", transform_string)
            if not match:
                raise ValueError(f"Malformed translate transformation: {transform_string}")
            coords = match.group(1).split(",")
            m = np.array([
                [1, 0, 0],
                [0, 1, 0],
                [float(coords[0]), float(coords[1]) if len(coords) > 1 else 0, 1]
            ])
            self.matrix = self.matrix @ m

        if "rotate" in transform_string:
            match = re.search(r"rotate\((.*?),(.*?),(.*?)\)", transform_string)
            if not match:
                match = re.search(r"rotate\((.*?)\)", transform_string)
                coord = 0, 0
            else:
                coord = float(match.group(2)), float(match.group(3))
            if not match:
                raise ValueError(f"Malformed rotate transformation: {transform_string}")
            angle = float(match.group(1)) * np.pi / 180
            pre = TransGL3().init(x_c=-coord[0], y_c=-coord[1])
            post = TransGL3().init(x_c=coord[0], y_c=coord[1])
            cos = np.cos(angle)
            sin = np.sin(angle)
            m = np.array([
                [cos, sin, 0],
                [-sin, cos, 0],
                [0, 0, 1]
            ])
            self.matrix = self.matrix @ m

        if ("matrix" not in transform_string
            and "translate" not in transform_string
            and "rotate" not in transform_string
            and transform_string != ""):
            raise ValueError(f"Unknown transformation: {transform_string}")

        # the matrix represents the transformation from (x, y, const) to (x, y const)
        # we preserve the const via a 1 so that convolutions work correctly
        if pre is not None and post is not None:
            self.matrix = pre.matrix @ self.matrix @ post.matrix

    def init(self, x_dx: float = 1, y_dy: float = 1, x_dy: float = 0, y_dx: float = 0, x_c: float = 0, y_c: float = 0):
        """Creates a transformation matrix directly from the values, rather than parsing a string."""
        self.matrix = np.array([
            [x_dx, y_dx, 0],
            [x_dy, y_dy, 0],
            [x_c , y_c , 1]
        ])
        return self

    def transform(self, point: tuple[float, float]) -> tuple[float, float]:
        """Applies the transformation to a point."""
        point_array = np.concatenate((point, (1,)))
        return tuple((point_array @ self.matrix)[:2].tolist())

    # represents a convolution
    # (t1 * t2).transform(p) == t1.transform(t2.transform(p))
    def __mul__(self, other):
        out = TransGL3()
        out.matrix = self.matrix @ other.matrix
        return out

    def __str__(self):
        return f"matrix({','.join(map(str, self.matrix[:, :2].flatten()))})"
