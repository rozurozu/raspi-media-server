import os


class FilterModule(object):
    """Custom path-related filters used in playbooks."""

    def filters(self):
        return {
            "path_is_absolute": self.path_is_absolute,
        }

    @staticmethod
    def path_is_absolute(value):
        """Return True if the given path is absolute, else False.

        Accepts any value that can be stringified. None and empty values return False.
        """
        if value is None:
            return False
        try:
            s = str(value)
        except Exception:
            return False
        if not s:
            return False
        return os.path.isabs(s)

