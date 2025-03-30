import json
import os
import time
import traceback
from loguru import logger
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

CUR_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(CUR_DIR, "logs")
ERRORS_DIR = os.path.join(CUR_DIR, "errors")

if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)
if not os.path.exists(ERRORS_DIR):
    os.makedirs(ERRORS_DIR)

# Configure loguru
logger.remove()  # Remove default handler
logger.add(
    os.path.join(LOGS_DIR, "xiaohongshu_publisher.log"),
    rotation="10 MB",
    retention="1 week",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)
logger.add(lambda msg: print(msg), level="INFO", format="{time:HH:mm:ss} | {level} | {message}")

# Constants
XIAOHONGSHU_COOKIE_PATH = "/your_path/cookies.json"
WAIT_TIMEOUT = 30  # seconds for explicit waits


# 按文件名数字部分排序（适用于"图片1.jpg"、"图片2.jpg"格式）
sorted_func = lambda x: int(''.join(filter(str.isdigit, x)) or 0)

class XiaohongshuPublisher:
    def __init__(self, headless: bool = False):
        self.driver = self._setup_edge_driver(headless)
        
    def _setup_edge_driver(self, headless: bool) -> webdriver.Edge:
        """Setup and configure the Edge webdriver"""
        options = webdriver.EdgeOptions()  # 使用edge浏览器
        # options = webdriver.Chrome('/usr/local/bin/chromedriver')  # 使用chrome浏览器
        if headless:
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
        
        driver = webdriver.Edge(options=options)
        driver.maximize_window()
        return driver
    
    def login(self) -> None:
        """Login to Xiaohongshu using cookies or manual login"""
        if os.path.exists(XIAOHONGSHU_COOKIE_PATH):
            logger.info("Loading cookies from file")
            try:
                with open(XIAOHONGSHU_COOKIE_PATH) as f:
                    cookies = json.loads(f.read())
                
                self.driver.get("https://creator.xiaohongshu.com/creator/post")
                self.driver.implicitly_wait(10)
                self.driver.delete_all_cookies()
                time.sleep(2)
                
                for cookie in cookies:
                    if 'expiry' in cookie:
                        del cookie["expiry"]
                    self.driver.add_cookie(cookie)
                
                logger.info("Navigating to creator dashboard")
                
                # 再跳转到发布页面
                self.driver.get("https://creator.xiaohongshu.com/publish/publish")
                time.sleep(3)  # 增加等待时间
                
                # 使用多种定位方式尝试查找"发布笔记"元素
                try:
                    # 尝试方法1: 使用多种XPath表达式
                    locators = [
                        (By.XPATH, '//*[contains(text(),"发布笔记")]'),
                        (By.XPATH, '//span[text()="发布笔记"]'),
                        (By.XPATH, '//div[contains(@class,"publish")]//span[contains(text(),"发布")]'),
                        (By.XPATH, '//button[contains(.,"发布笔记")]'),
                        (By.CSS_SELECTOR, '[class*="publish"] span'),
                        # 尝试通过URL判断是否在发布页面
                        (By.TAG_NAME, 'body')  # 如果其他都失败，至少确认页面加载完成
                    ]
                    
                    element_found = False
                    for locator in locators:
                        try:
                            WebDriverWait(self.driver, 10).until(
                                EC.presence_of_element_located(locator)
                            )
                            element_found = True
                            logger.info(f"Found element using {locator}")
                            break
                        except:
                            continue
                    
                    # 检查URL是否包含publish关键字，也可以作为登录成功的标志
                    current_url = self.driver.current_url
                    if "publish" in current_url or element_found:
                        logger.info("Login successful with cookies")
                        # 保存页面源码以便调试
                        with open("page_source.html", "w", encoding="utf-8") as f:
                            f.write(self.driver.page_source)
                        return
                    else:
                        logger.warning("URL check failed, may not be logged in properly")
                        raise Exception("Failed to verify login state")
                        
                except Exception as e:
                    logger.error(f"Error finding elements: {e}")
                    # 截图保存，方便调试
                    self.driver.save_screenshot("login_error.png")
                    raise e
            
                
            except Exception as e:
                logger.error(f"Error loading cookies: {e}")
                # self.manual_login()
        else:
            logger.info("No cookies found, proceeding with manual login")
            # self.manual_login()
    
    def manual_login(self) -> None:
        """Handle manual login process"""
        self.driver.get('https://creator.xiaohongshu.com/creator/post')
        logger.info("Waiting for manual login (30 seconds)...")
        time.sleep(60)
        logger.info("Login time completed")
        
        # Save cookies for future use
        try:
            cookies = self.driver.get_cookies()
            os.makedirs(os.path.dirname(XIAOHONGSHU_COOKIE_PATH), exist_ok=True)
            with open(XIAOHONGSHU_COOKIE_PATH, 'w') as f:
                f.write(json.dumps(cookies))
            logger.info("Cookies saved successfully")
        except Exception as e:
            logger.error(f"Failed to save cookies: {e}")
    
    def _get_publish_date(self) -> str:
        """Calculate the next publishing date (today or tomorrow at 20:00)"""
        now = datetime.today()
        # if now.hour > 20:
        #     # If it's past 8 PM, schedule for tomorrow
        #     target_date = now + timedelta(days=1)
        # else:
        target_date = now
        
        target_date = target_date.replace(hour=20, minute=0, second=0, microsecond=0)
        return target_date.strftime("%Y-%m-%d %H:%M")
    
    def _add_tags(self, content_element, tags: List[str]) -> None:
        """Add tags to the content"""
        for tag in tags:
            try:
                content_element.send_keys(tag)
                time.sleep(2)
                
                # Find and click on the tag suggestion
                tag_elements = self.driver.find_elements(By.CLASS_NAME, "publish-topic-item")
                tag_clicked = False
                
                for tag_element in tag_elements:
                    if tag in tag_element.text:
                        logger.info(f"Clicking tag: {tag}")
                        tag_element.click()
                        tag_clicked = True
                        break
                
                if not tag_clicked:
                    logger.warning(f"Tag '{tag}' not found in suggestions")
                
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error adding tag '{tag}': {e}")
    
    def _set_scheduled_publishing(self) -> None:
        """Configure scheduled publishing"""
        try:
            # Find the scheduling option (4th element with this class)
            scheduling_options = WebDriverWait(self.driver, WAIT_TIMEOUT).until(
                EC.presence_of_all_elements_located((By.XPATH, '//*[@class="css-1v54vzp"]'))
            )
            
            if len(scheduling_options) >= 4:
                logger.info("Clicking scheduled publishing option")
                scheduling_options[3].click()
                time.sleep(2)
                
                # Set the publishing date
                date_input = WebDriverWait(self.driver, WAIT_TIMEOUT).until(
                    EC.presence_of_element_located((By.XPATH, '//*[@placeholder="请选择日期"]'))
                )
                date_input.send_keys(Keys.CONTROL, 'a')
                date_input.send_keys(self._get_publish_date())
                time.sleep(2)
            else:
                logger.warning("Scheduling options not found")
        except Exception as e:
            logger.error(f"Error setting scheduled publishing: {e}")
    
    def publish_video(self, video_path: str, title: str, tags: List[str]) -> bool:
        """Publish a video to Xiaohongshu"""
        try:
            # Click on publish note button
            WebDriverWait(self.driver, WAIT_TIMEOUT).until(
                EC.element_to_be_clickable((By.XPATH, '//*[text()="发布笔记"]'))
            ).click()
            logger.info(f"Starting video upload: {video_path}")
            time.sleep(3)
            
            # Upload video file
            file_input = WebDriverWait(self.driver, WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.XPATH, '//input[@type="file"]'))
            )
            file_input.send_keys(video_path)
            
            # Set title
            WebDriverWait(self.driver, WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.XPATH, '//*[@placeholder="填写标题，可能会有更多赞哦～"]'))
            ).send_keys(title)
            
            # Set description
            content_element = WebDriverWait(self.driver, WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.XPATH, '//*[@placeholder="填写更全面的描述信息，让更多的人看到你吧！"]'))
            )
            content_element.send_keys(title)
            
            # Add tags
            self._add_tags(content_element, tags)
            
            # Set scheduled publishing
            self._set_scheduled_publishing()
            
            # Wait for video upload to complete
            logger.info("Waiting for video processing to complete...")
            max_wait_time = 600  # 10 minutes max wait
            start_time = time.time()
            
            while time.time() - start_time < max_wait_time:
                try:
                    # Check if "重新上传" (re-upload) button appears, indicating upload completion
                    self.driver.find_element(By.XPATH, 
                        '//*[@id="publish-container"]/div/div[2]/div[2]/div[6]/div/div/div[1]//*[contains(text(),"重新上传")]')
                    logger.info("Video upload completed")
                    break
                except NoSuchElementException:
                    logger.info("Video still uploading...")
                    time.sleep(10)
            else:
                logger.warning("Video upload timed out")
            
            # Click publish button
            WebDriverWait(self.driver, WAIT_TIMEOUT).until(
                EC.element_to_be_clickable((By.XPATH, '//*[text()="发布"]'))
            ).click()
            
            logger.info("Video published successfully")
            time.sleep(5)
            return True
            
        except Exception as e:
            logger.error(f"Error publishing video: {e}")
            traceback.print_exc()
            return False
    
    def publish_images(self, image_folder: str, title: str, description: str, tags: List[str]) -> bool:
        """Publish images to Xiaohongshu"""
        try:
            # Click on publish note button
            WebDriverWait(self.driver, WAIT_TIMEOUT).until(
                EC.element_to_be_clickable((By.XPATH, '//*[contains(text(),"发布笔记")]'))
            ).click()
            logger.info(f"Starting image upload from folder: {image_folder}")
            time.sleep(3)
            
            # Click on upload images button
            WebDriverWait(self.driver, WAIT_TIMEOUT).until(
                EC.element_to_be_clickable((By.XPATH, '//*[text()="上传图文"]'))
            ).click()
            
            # Upload image files
            file_input = WebDriverWait(self.driver, WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.XPATH, '//input[@type="file"]'))
            )
            
            # Get all image files from the folder
            file_names = sorted([f for f in os.listdir(image_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg'))], key=sorted_func)
            if not file_names:
                logger.error(f"No image files found in {image_folder}")
                return False

            # 逐张上传，上传一张后，该元素不再附加到DOM，页面变了。
            # for file_name in file_names:
            #     file_path = os.path.join(image_folder, file_name)
            #     file_input.send_keys(file_path)
            #     logger.info(f"Uploaded image: {file_name}")
            #     time.sleep(3)
            
            # 多张上传
            file_paths = [os.path.join(image_folder, file_name) for file_name in file_names]
            file_input.send_keys('\n'.join(file_paths))
            logger.info(f"Uploaded {len(file_paths)} images at once")
            time.sleep(len(file_paths) * 2)

            # Set title
            WebDriverWait(self.driver, WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.XPATH, '//*[@placeholder="填写标题会有更多赞哦～"]'))
            ).send_keys(title)
            
            # Set description
            content_element = WebDriverWait(self.driver, WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.XPATH, '//*[@data-placeholder="输入正文描述，真诚有价值的分享予人温暖"]'))
            )
            content_element.send_keys(description)
            
            # Add tags
            self._add_tags(content_element, tags)
            
            # Set scheduled publishing
            self._set_scheduled_publishing()
            
            # Click publish button
            WebDriverWait(self.driver, WAIT_TIMEOUT).until(
                EC.element_to_be_clickable((By.XPATH, '//*[text()="发布"]'))
            ).click()
            
            logger.info("Images published successfully")
            time.sleep(5)
            return True
            
        except Exception as e:
            logger.error(f"Error publishing images: {e}")
            traceback.print_exc()
            self.driver.save_screenshot(os.path.join(ERRORS_DIR, "publish_error.png"))
            with open(os.path.join(ERRORS_DIR, "page_source_error.html"), "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)

            return False
    
    def close(self) -> None:
        """Close the webdriver"""
        if self.driver:
            self.driver.quit()
            logger.info("WebDriver closed")


def main():
    publisher = None
    try:
        # Example usage
        publisher = XiaohongshuPublisher(headless=False)
        # publisher.manual_login()
        publisher.login()
        
        # For image publishing
        image_folder = "/your_path/"
        image_title = "奇点更近"
        image_description = "回看当下，或许我们已经越过奇点"
        image_tags = ['#奇点', '#未来世界']
        publisher.publish_images(image_folder, image_title, image_description, image_tags)
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        traceback.print_exc()
    finally:
        if publisher:
            publisher.close()


if __name__ == "__main__":
    main()
