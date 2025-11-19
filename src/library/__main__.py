from library.api import LibraryAPI
from library.manager.database import Database
import inspect
import os


if __name__ == "__main__":
    """test the library with root media fodler"""

    # Read database
    api = LibraryAPI()  # create api instance
    api.read()  # print in terminal
    list = api.get_list()  # get dict list
    print(list)  # print dict list
