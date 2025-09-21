from pathlib import Path
import aiofiles


async def async_export_txt(*, filename: str, value: str) -> None:
    """Asynchronously write a string to a txt file for debugging purposes."""
    output_dir = Path(__file__).parent.parent.parent / "outputs"
    output_dir.mkdir(exist_ok=True)  # Create directory if it doesn't exist

    output_path = output_dir / f"{filename}.txt"
    async with aiofiles.open(output_path, "w") as file:
        await file.write(value)
