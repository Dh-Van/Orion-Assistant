import dotenv, os, base64
from loguru import logger
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.services.daily import DailyParams
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.services.google.stt import GoogleSTTService
from pipecat.services.google.tts import GoogleTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.transcriptions.language import Language
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.services.llm_service import FunctionCallParams
from pipecat.adapters.schemas.tools_schema import ToolsSchema



dotenv.load_dotenv(".credentials.env")
dotenv.load_dotenv(".env")

transport_params = {
    "daily": lambda: DailyParams(
        audio_in_enabled=True, audio_out_enabled=True, vad_analyzer=SileroVADAnalyzer()
    ),
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        vad_analyzer=SileroVADAnalyzer(),
    ),
}

async def get_last_name(params: FunctionCallParams):
    first_name = params.arguments['first_name']
    await params.result_callback(f'full name is {first_name} Shah')


async def run_bot(transport: BaseTransport):
    logger.info("Starting bot")

    stt = GoogleSTTService(
        params=GoogleSTTService.InputParams(languages=Language.EN_US),
        credentials=base64.b64decode(os.getenv("GOOGLE_CREDENTIALS")),
    )

    tts = GoogleTTSService(
        voice_id="en-US-Chirp3-HD-Charon",
        params=GoogleTTSService.InputParams(language=Language.EN_US),
        credentials=base64.b64decode(os.getenv("GOOGLE_CREDENTIALS")),
    )

    llm = GoogleLLMService(
        api_key=os.getenv("GEMINI_API_KEY"), model="gemini-2.5-flash"
    )
    
    llm.register_function('get_last_name', get_last_name)
    
    @llm.event_handler('on_function_calls_started')
    async def on_function_calls_started(service, function_calls):
        logger.info('trued to call function')
        # await tts.queue_frame(TTSpea)
    
    last_name_function = FunctionSchema(
        name = 'get_last_name',
        description = 'get last name based off of the first name',
        properties={
            'first_name': {
                'type': 'string',
                'description': 'First name of the user'
            }
        },
        required=['first_name']
    )
    
    tools = ToolsSchema(standard_tools=[last_name_function])

    messages = [
        {
            "role": "system",
            "content": "You are a helpful LLM in a WebRTC call. Your goal is to demonstrate your capabilities in a succinct way. Your output will be converted to audio so dont include special characters in your answers. Respond to what the user said in a creative and helpful way. You have access to the get_last_name tool which can return the last name of the user based off of the first name",
        }
    ]

    context = OpenAILLMContext(messages, tools)
    context_aggregator = llm.create_context_aggregator(context)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline, params=PipelineParams(enable_metrics=True, enable_usage_metrics=True)
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("client connected")

        messages.append(
            {
                "role": "system",
                "content": "introduce yourself to the client in a few words",
            }
        )

        await task.queue_frames([context_aggregator.user().get_context_frame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)

    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    transport = await create_transport(runner_args, transport_params)

    await run_bot(transport)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
