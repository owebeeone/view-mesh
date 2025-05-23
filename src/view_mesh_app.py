#!/usr/bin/env python

"""
ViewMesh application entry point.
"""

import asyncio
from view_mesh.viewmesh import main

if __name__ == "__main__":
    asyncio.run(main()) 