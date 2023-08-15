"""gr.Carousel() component."""

from gradio_client.serializing import SimpleSerializable

from gradio.blocks import updateable
from gradio.components.base import IOComponent
from gradio.events import Changeable


class Carousel(IOComponent, Changeable, SimpleSerializable):
    """
    Deprecated Component
    """

    @updateable
    def __init__(
        self,
        *args,
        **kwargs,
    ):
        raise DeprecationWarning(
            "The Carousel component is deprecated. Please consider using the Gallery "
            "component, which can be used to display images (and optional captions).",
        )
