# Synthetic Aperture Tilt-Shift from a Handheld Phone Video

ELEC 549 project report · Daniel Kuo · 23 September 2026

## 1. Creative goal

I wanted to replicate tilt-shift photography with a video from an iPhone. I wanted to get the miniature, model-village look and app filters only paint a blur band across the picture. The goal was the real optical effect: every object blurred by its true distance.

![Figure 1. Final image: the O'Connor lobby from an upper floor. Focus plane tilted 26° off the lens axis; average of 169 aligned video frames.](report/final.jpg)

## 2. How it works

**A lens is an averaging machine.** Light enters a lens at every point across its opening. Each point sees the scene from a slightly different position, and the sensor adds all of these views together. An object at the focus distance looks the same from every point of the opening, so the views agree and it stays sharp. An object nearer or farther is seen from different angles, the views disagree about where it is, and the sum smears it. That smear is defocus blur, and it grows with the size of the opening. A phone lens is a few millimetres wide, so its views almost agree and almost nothing blurs.

**A video sweep is a large lens, one view at a time.** I move the phone across a disc about an arm's reach wide while it records. Each frame is the view from one point of a lens that size. Adding the frames together gives the image that lens would make. A 0.5 m opening is a hundred times wider than any real lens, which is why the blur becomes strong enough to look like a miniature.

**Aligning the frames sets the focus.** Before adding, the frames must be shifted so that one chosen part of the scene lands in the same place in every frame. Whatever is aligned comes out sharp. Everything else comes out blurred.

**The blur is real parallax.** When the camera moves sideways by t, a point at distance z moves in the image by about f·t/z pixels, where f is the focal length in pixels. Near points move a lot, far points a little. If every frame is shifted back by the amount that suits distance z~0~, points at z~0~ land on top of each other, but a point at another distance z is still off by f·t·|1/z − 1/z~0~|. Across the whole sweep, t covers a disc of diameter D, so that point is spread over

    b = D · f · |1/z − 1/z~0~|  pixels.

This is the circle-of-confusion formula of a real lens, with D in place of the aperture diameter. No depth map is estimated and no blur filter is applied. The blur is simply the frames disagreeing, by exactly the amount their parallax disagrees.

**Tilting the plane.** One shift per frame can only align one distance, so the sharp region is a slab facing the camera, like an ordinary lens. A tilted plane is at a different distance at every pixel, so every pixel needs its own correction. For a flat plane, all of these corrections together are one 3×3 matrix, a homography:

    H = K (R + t n^T^ / d) K^-1^

Read from right to left: K^-1^ turns a pixel of the reference frame into a ray in space. R turns the ray by the amount the phone rotated between the two frames. t n^T^/d adds the parallax, which grows with the translation t and shrinks with the distance to the plane along that ray; the normal n and distance d describe the plane. K turns the result back into a pixel of the other frame. Warping each frame by its H puts every point of the plane back where the reference frame saw it, so the plane comes out sharp after averaging.

**Why this reaches planes a lens cannot.** H does not depend on the pictures. It is built only from the camera motion, the lens, and the numbers (n, d) that describe the plane. So the plane can be anywhere: tilted, passing through empty air, or lying along a floor with no texture to track. Changing the tilt is changing n. One recording gives every plane.

## 3. Capture

The lobby was filmed from the upper-floor balcony with an iPhone at 4K, 24 fps, on the 1× lens, for about 45 seconds. During the take the phone was moved across a disc roughly an arm's reach wide, spiralling out from the centre, while kept pointed at the same spot in the lobby. Only the phone's position matters; small rotations are corrected by the alignment later. Every fifth frame was extracted, giving 213 frames spread over the disc.

The scene was chosen on purpose: looking steeply down from a height at furniture on two floors, with a column very close to the camera, gives depths from a couple of metres to about fifteen in one frame. That depth range is what the effect needs (Section 7).

## 4. Technical steps

**How you would do it by hand.** Nothing in this method needs a computer to be understood, because a version of it can be done in Photoshop. Extract a few dozen frames from the video and load them as layers. Pick the thing you want sharp, say the green sofa, and nudge every layer until its sofa sits exactly on top of the sofa in the first layer. Then set the stack to average the layers (Stack Mode → Mean, or give layer *k* an opacity of 1/*k*). The sofa, which now agrees in every layer, comes out sharp; the table on the floor below, which every layer put in a slightly different place, comes out as a soft smear. That is already a synthetic aperture photograph, and it is the first thing I built, as code that does the nudging by template matching.

Tilting the plane is the same idea with a different tool. Nudging a layer is a shift, and a shift can only line up things at one depth, so the sharp region is a slab facing the camera, like an ordinary lens. To line up a whole tilted plane, use Free Transform → Distort instead: pick four points lying on the plane you want sharp, for instance four corners of the floor tiles, and drag the corners of each layer until those four points land on their positions in the first layer. A four-corner distortion is exactly a homography, so this lines up every point of that plane at once, near and far, and averaging the stack gives an image focused on the tilted plane. It is only tedious: four points on each of two hundred layers.

It also shows where doing it by eye stops working. You can only drag a layer onto something you can see. A plane that passes through the empty middle of the atrium, or along a blank white wall, has nothing at the focus distance to line up on. In those places the correct distortion still exists, it just cannot be found by looking at the pictures. That is the limit of SynthCam too, and the reason the code computes the warp from where the camera was rather than from what it saw.

**What the code does instead.** My tool automates exactly those steps. It pulls every fifth frame out of the video, then works out where the phone was for each frame: COLMAP finds thousands of small features in every frame, matches them between neighbours, and solves, like a surveyor triangulating from many vantage points, for each camera's position and orientation, the lens's focal length, and the 3D position of the matched features. (Its defaults assume photographs taken metres apart and refused to start from views only a degree apart, so its angle thresholds had to be lowered; after that it placed all 213 frames to within 1.3 px.) The plane is then described as numbers rather than four dragged points: I click where I want focus, which reads the depth there from the triangulated features, and set the tilt with sliders while a preview updates. The four-corner distortion for each frame is computed from that frame's position and the plane's numbers, exactly and where there is nothing to drag onto, and the warped frames are averaged in linear light, since averaging gamma-encoded pixels makes blurred regions too dark, with each pixel divided by the number of frames that actually reached it. Because the slow step, recovering the camera positions, is done once, the plane can be changed and re-rendered as often as wanted; a 4K render takes a few seconds, and a browser version renders the sweep live.

## 5. The final image in numbers

Structure-from-motion recovers shape but not absolute scale, so distances are in arbitrary units; the blur in pixels only depends on the ratio D/z.

| Quantity | Value |
| --- | --- |
| Frames | 213 extracted, 213 registered by COLMAP, 169 used (aperture 0.8) |
| Intrinsics | f = 2658 px, radial distortion k = 0.015, reprojection error 1.27 px |
| Sweep diameter | 10.4 units for the full sweep, 7.8 for the frames used |
| Scene depth | 230–640 units (5th–95th percentile of the sparse points) |
| Focus plane | tilt 26°, azimuth 351°, depth 284 at the pivot (upper floor by the sofa) |

Predicted blur b = D f |1/z − 1/z~0~| at a few points: 0 px at the pivot, 1 px at the top of the stairs, 10 px at the reception desk, 33 px at the table on the lower floor (at 4K resolution).

![Figure 2. Full-resolution crops, reference frame left and render right. Top: the lower-floor table (predicted 33 px) is smeared into a soft disc. Bottom: the sofa on the focus plane stays sharp; a person who walked past during the sweep survives as a translucent ghost.](report/crops.jpg)

![Figure 3. A second scene, the Commons dining hall, from one video and two planes. Left: tilted 38.5° along the floor, so tables near and far are sharp while the banners in front and the courtyard beyond blur. Right: tilted 63.5° the other way; the sharp band now runs across the mezzanine and the floor is out of focus.](report/commons.jpg)

## 6. Validation

Before trusting real footage I rendered a synthetic city (a textured ground plane seen from above, with upright buildings) from known camera positions and ran the full pipeline on the encoded video. COLMAP recovered f = 1001 px against a true 1000 and registered all 60 frames; clicking three ground points gave a plane tilted 54.8° against the true 55°. A second test renders dots at known depths by direct projection, sharing no code with the homography, and measures their rendered width: it matches D f |1/z − 1/z~0~| within 6 %, and a template-matched shift-and-add of the same frames agrees with the pose-derived warp to within one grey level.

![Figure 4. Tilt sweep of the synthetic scene from one capture, 0° to 60°, rendered in one pass over the frames.](report/demo_strip.jpg)

## 7. What I learned

**The scene decides whether the effect exists at all.** The blur at a point is D·f·|1/z − 1/z~0~|: it comes from the *difference* between that point's depth and the focus depth, scaled by how big the sweep is compared with the distance. A scene where everything is at nearly the same depth, a wall seen head-on or a distant view, produces almost no blur no matter how the plane is set, because the frames agree about everything. A test capture of the quad from a roof, some 50 m away, came out almost uniformly sharp for exactly this reason. The lobby works because from the balcony there are objects at two metres (the column), at five (the upper-floor furniture) and at fifteen (the study table below), all in one frame. Even so, the predicted 33 px of blur on the lower floor is visible but modest; the miniature look would be stronger with a wider sweep or a nearer subject. Looking down from a height at small objects, the classic tilt-shift viewpoint, is the right choice for optical reasons, not only for the look.

**Moving people do not blur, they ghost.** A real lens takes all of its views at the same instant, so a person is at one place in every view and simply blurs if they are off the plane. My aperture is assembled over 45 seconds. Someone who walks through is at a different place in each frame, and in most frames not there at all, so the average contains a faint, transparent copy of them at each position they occupied (Figure 2, bottom right, and the diners in Figure 3). This is not a bug in the alignment; it is the honest result of averaging views taken at different times. Taking the median of the frames instead of the mean drops anything that is present in fewer than half the frames, at the cost of changing the character of the blur; shooting when nobody is moving is the simpler fix.

**The focus plane can go where no lens can put it.** A lens's focus plane is fixed by its geometry: perpendicular to the axis, or tilted only within the limits of a tilt-shift mechanism, and always a plane the lens is physically pointed at. Here the plane is three numbers. In Figure 3 (right) it passes through the open air of the atrium and across walls with nothing on them to track, and in the lobby it runs along a floor at 26° to the line of sight. SynthCam cannot do this, because it aligns on image features and there has to be something at the focus distance to tap. Computing the warp from camera pose removes that requirement; the price is that the pose has to be recovered first, which is the slow and fragile step. Once it is, the render is cheap enough that the whole family of images from one recording can be explored live with a slider, which turned out to be the most convincing demonstration of what a synthetic aperture is.

**The alignment is only as good as the recovered camera positions.** Any error in a frame's R and t misplaces that frame's contribution and softens the very plane that should be sharp. The frames at the far edge of the sweep were the least accurately placed, which is why the final image uses the inner 80 % of the sweep, and why a second take of the same lobby, on which COLMAP registered only a handful of frames, could not be used at all. For this method the reconstruction stage, not the rendering, is where the risk lives.
