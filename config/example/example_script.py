from autogui.scripting.runtime import ScriptBase


class ExampleScript(ScriptBase):
    def run(self):
        run_count = self.ctx.state.get("example_script_runs", 0) + 1
        self.ctx.state["example_script_runs"] = run_count

        sample_pic = self.ctx.get_resource("sample_pic")
        self.ctx.log.info(f"ExampleScript 第 {run_count} 次运行，图片资源: {sample_pic.search_target}")

        pic_match = self.ctx.find_image(resource="sample_pic")
        ocr_match = self.ctx.find_text(resource="sample_ocr")
        self.ctx.state["example_script_last_pic_found"] = pic_match is not None
        self.ctx.state["example_script_last_ocr_found"] = ocr_match is not None

        self.ctx.state["example_script_main_exists"] = self.ctx.resolve_path("main.csv").exists()
        screenshot = self.ctx.screenshot()
        self.ctx.state["example_script_last_screenshot_shape"] = getattr(screenshot, "shape", None)

        if run_count == 1:
            self.ctx.log.debug("第一次运行：返回 next_step()")
            return self.next_step()

        if run_count == 2:
            self.ctx.log.debug("第二次运行：启动 input_actions.csv 子流程")
            return self.start_subflow("input_actions.csv")

        self.ctx.log.debug("第三次运行：使用 jmp 资源跳回主流程")
        self.ctx.sleep(0.1)
        return self.jump_resource("return_main")


def run(ctx):
    return ExampleScript(ctx).run()
