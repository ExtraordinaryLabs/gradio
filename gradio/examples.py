"""
Defines helper methods useful for loading and caching Interface examples.
"""
from __future__ import annotations

import ast
import csv
import os
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, List

from gradio import utils
from gradio.components import Dataset
from gradio.context import Context
from gradio.documentation import document, set_documentation_group
from gradio.flagging import CSVLogger

if TYPE_CHECKING:  # Only import for type checking (to avoid circular imports).
    from gradio.components import IOComponent

CACHED_FOLDER = "gradio_cached_examples"
LOG_FILE = "log.csv"

set_documentation_group("component-helpers")


def create_examples(
    examples: List[Any] | List[List[Any]] | str,
    inputs: IOComponent | List[IOComponent],
    outputs: IOComponent | List[IOComponent] | None = None,
    fn: Callable | None = None,
    cache_examples: bool = False,
    examples_per_page: int = 10,
    _api_mode: bool = False,
    label: str | None = None,
    elem_id: str | None = None,
    run_on_click: bool = False,
    preprocess: bool = True,
    postprocess: bool = True,
    batch: bool = False,
):
    """Top-level synchronous function that creates Examples. Provided for backwards compatibility, i.e. so that gr.Examples(...) can be used to create the Examples component."""
    examples_obj = Examples(
        examples=examples,
        inputs=inputs,
        outputs=outputs,
        fn=fn,
        cache_examples=cache_examples,
        examples_per_page=examples_per_page,
        _api_mode=_api_mode,
        label=label,
        elem_id=elem_id,
        run_on_click=run_on_click,
        preprocess=preprocess,
        postprocess=postprocess,
        batch=batch,
        _initiated_directly=False,
    )
    utils.synchronize_async(examples_obj.create)
    return examples_obj


@document()
class Examples:
    """
    This class is a wrapper over the Dataset component and can be used to create Examples
    for Blocks / Interfaces. Populates the Dataset component with examples and
    assigns event listener so that clicking on an example populates the input/output
    components. Optionally handles example caching for fast inference.

    Demos: blocks_inputs, fake_gan
    Guides: more_on_examples_and_flagging, using_hugging_face_integrations, image_classification_in_pytorch, image_classification_in_tensorflow, image_classification_with_vision_transformers, create_your_own_friends_with_a_gan
    """

    def __init__(
        self,
        examples: List[Any] | List[List[Any]] | str,
        inputs: IOComponent | List[IOComponent],
        outputs: IOComponent | List[IOComponent] | None = None,
        fn: Callable | None = None,
        cache_examples: bool = False,
        examples_per_page: int = 10,
        _api_mode: bool = False,
        label: str | None = "Examples",
        elem_id: str | None = None,
        run_on_click: bool = False,
        preprocess: bool = True,
        postprocess: bool = True,
        batch: bool = False,
        _initiated_directly: bool = True,
    ):
        """
        Parameters:
            examples: example inputs that can be clicked to populate specific components. Should be nested list, in which the outer list consists of samples and each inner list consists of an input corresponding to each input component. A string path to a directory of examples can also be provided but it should be within the directory with the python file running the gradio app. If there are multiple input components and a directory is provided, a log.csv file must be present in the directory to link corresponding inputs.
            inputs: the component or list of components corresponding to the examples
            outputs: optionally, provide the component or list of components corresponding to the output of the examples. Required if `cache` is True.
            fn: optionally, provide the function to run to generate the outputs corresponding to the examples. Required if `cache` is True.
            cache_examples: if True, caches examples for fast runtime. If True, then `fn` and `outputs` need to be provided
            examples_per_page: how many examples to show per page.
            label: the label to use for the examples component (by default, "Examples")
            elem_id: an optional string that is assigned as the id of this component in the HTML DOM.
            run_on_click: if cache_examples is False, clicking on an example does not run the function when an example is clicked. Set this to True to run the function when an example is clicked. Has no effect if cache_examples is True.
            preprocess: if True, preprocesses the example input before running the prediction function and caching the output. Only applies if cache_examples is True.
            postprocess: if True, postprocesses the example output after running the prediction function and before caching. Only applies if cache_examples is True.
            batch: If True, then the function should process a batch of inputs, meaning that it should accept a list of input values for each parameter. Used only if cache_examples is True.
        """
        if _initiated_directly:
            warnings.warn(
                "Please use gr.Examples(...) instead of gr.examples.Examples(...) to create the Examples.",
            )

        if cache_examples and (fn is None or outputs is None):
            raise ValueError("If caching examples, `fn` and `outputs` must be provided")

        if not isinstance(inputs, list):
            inputs = [inputs]
        if outputs and not isinstance(outputs, list):
            outputs = [outputs]

        working_directory = Path().absolute()

        if examples is None:
            raise ValueError("The parameter `examples` cannot be None")
        elif isinstance(examples, list) and (
            len(examples) == 0 or isinstance(examples[0], list)
        ):
            pass
        elif (
            isinstance(examples, list) and len(inputs) == 1
        ):  # If there is only one input component, examples can be provided as a regular list instead of a list of lists
            examples = [[e] for e in examples]
        elif isinstance(examples, str):
            if not Path(examples).exists():
                raise FileNotFoundError(
                    "Could not find examples directory: " + examples
                )
            working_directory = examples
            if not (Path(examples) / LOG_FILE).exists():
                if len(inputs) == 1:
                    examples = [[e] for e in os.listdir(examples)]
                else:
                    raise FileNotFoundError(
                        "Could not find log file (required for multiple inputs): "
                        + LOG_FILE
                    )
            else:
                with open(Path(examples) / LOG_FILE) as logs:
                    examples = list(csv.reader(logs))
                    examples = [
                        examples[i][: len(inputs)] for i in range(1, len(examples))
                    ]  # remove header and unnecessary columns

        else:
            raise ValueError(
                "The parameter `examples` must either be a string directory or a list"
                "(if there is only 1 input component) or (more generally), a nested "
                "list, where each sublist represents a set of inputs."
            )

        input_has_examples = [False] * len(inputs)
        for example in examples:
            for idx, example_for_input in enumerate(example):
                if not (example_for_input is None):
                    try:
                        input_has_examples[idx] = True
                    except IndexError:
                        pass  # If there are more example components than inputs, ignore. This can sometimes be intentional (e.g. loading from a log file where outputs and timestamps are also logged)

        inputs_with_examples = [
            inp for (inp, keep) in zip(inputs, input_has_examples) if keep
        ]
        non_none_examples = [
            [ex for (ex, keep) in zip(example, input_has_examples) if keep]
            for example in examples
        ]

        self.examples = examples
        self.non_none_examples = non_none_examples
        self.inputs = inputs
        self.inputs_with_examples = inputs_with_examples
        self.outputs = outputs
        self.fn = fn
        self.cache_examples = cache_examples
        self._api_mode = _api_mode
        self.preprocess = preprocess
        self.postprocess = postprocess
        self.batch = batch

        with utils.set_directory(working_directory):
            self.processed_examples = [
                [
                    component.postprocess(sample)
                    for component, sample in zip(inputs, example)
                ]
                for example in examples
            ]
        self.non_none_processed_examples = [
            [ex for (ex, keep) in zip(example, input_has_examples) if keep]
            for example in self.processed_examples
        ]
        if cache_examples:
            for example in self.examples:
                if len([ex for ex in example if ex is not None]) != len(self.inputs):
                    warnings.warn(
                        "Examples are being cached but not all input components have "
                        "example values. This may result in an exception being thrown by "
                        "your function. If you do get an error while caching examples, make "
                        "sure all of your inputs have example values for all of your examples "
                        "or you provide default values for those particular parameters in your function."
                    )
                    break

        with utils.set_directory(working_directory):
            self.dataset = Dataset(
                components=inputs_with_examples,
                samples=non_none_examples,
                type="index",
                label=label,
                samples_per_page=examples_per_page,
                elem_id=elem_id,
            )

        self.cached_folder = Path(CACHED_FOLDER) / str(self.dataset._id)
        self.cached_file = Path(self.cached_folder) / "log.csv"
        self.cache_examples = cache_examples
        self.run_on_click = run_on_click

    async def create(self) -> None:
        """Caches the examples if self.cache_examples is True and creates the Dataset
        component to hold the examples"""

        async def load_example(example_id):
            if self.cache_examples:
                processed_example = self.non_none_processed_examples[
                    example_id
                ] + await self.load_from_cache(example_id)
            else:
                processed_example = self.non_none_processed_examples[example_id]
            return utils.resolve_singleton(processed_example)

        if Context.root_block:
            if self.cache_examples and self.outputs:
                targets = self.inputs_with_examples
            else:
                targets = self.inputs
            self.dataset.click(
                load_example,
                inputs=[self.dataset],
                outputs=targets,  # type: ignore
                postprocess=False,
                queue=False,
            )
            if self.run_on_click and not self.cache_examples:
                if self.fn is None:
                    raise ValueError("Cannot run_on_click if no function is provided")
                self.dataset.click(
                    self.fn,
                    inputs=self.inputs,  # type: ignore
                    outputs=self.outputs,  # type: ignore
                )

        if self.cache_examples:
            await self.cache()

    async def cache(self) -> None:
        """
        Caches all of the examples so that their predictions can be shown immediately.
        """
        if Path(self.cached_file).exists():
            print(
                f"Using cache from '{Path(self.cached_folder).resolve()}' directory. If method or examples have changed since last caching, delete this folder to clear cache."
            )
        else:
            if Context.root_block is None:
                raise ValueError("Cannot cache examples if not in a Blocks context")

            print(f"Caching examples at: '{Path(self.cached_file).resolve()}'")
            cache_logger = CSVLogger()

            # create a fake dependency to process the examples and get the predictions
            dependency = Context.root_block.set_event_trigger(
                event_name="fake_event",
                fn=self.fn,
                inputs=self.inputs_with_examples,  # type: ignore
                outputs=self.outputs,  # type: ignore
                preprocess=self.preprocess and not self._api_mode,
                postprocess=self.postprocess and not self._api_mode,
                batch=self.batch,
            )

            fn_index = Context.root_block.dependencies.index(dependency)
            assert self.outputs is not None
            cache_logger.setup(self.outputs, self.cached_folder)
            for example_id, _ in enumerate(self.examples):
                processed_input = self.processed_examples[example_id]
                if self.batch:
                    processed_input = [[value] for value in processed_input]
                prediction = await Context.root_block.process_api(
                    fn_index=fn_index, inputs=processed_input, request=None, state={}
                )
                output = prediction["data"]
                if self.batch:
                    output = [value[0] for value in output]
                cache_logger.flag(output)
            # Remove the "fake_event" to prevent bugs in loading interfaces from spaces
            Context.root_block.dependencies.remove(dependency)
            Context.root_block.fns.pop(fn_index)

    async def load_from_cache(self, example_id: int) -> List[Any]:
        """Loads a particular cached example for the interface.
        Parameters:
            example_id: The id of the example to process (zero-indexed).
        """
        with open(self.cached_file) as cache:
            examples = list(csv.reader(cache))
        example = examples[example_id + 1]  # +1 to adjust for header
        output = []
        assert self.outputs is not None
        for component, value in zip(self.outputs, example):
            try:
                value_as_dict = ast.literal_eval(value)
                assert utils.is_update(value_as_dict)
                output.append(value_as_dict)
            except (ValueError, TypeError, SyntaxError, AssertionError):
                output.append(component.serialize(value, self.cached_folder))
        return output
